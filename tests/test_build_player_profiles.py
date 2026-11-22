import json
import tempfile
import unittest
from pathlib import Path

from build_player_profiles import (
    ProfileBuildError,
    build_player_profile_document,
)


def _ranking(player_id, full_name, team_id, team_name):
    return {
        "player_id": player_id,
        "full_name": full_name,
        "team_id": team_id,
        "team_name": team_name,
        "played": 10,
        "wins": 5,
        "win_pct": 50.0,
        "rating": None,
        "prev_rating": None,
        "anonymous": False,
        "substitute": False,
        "own_team": True,
    }


def _season_document(season_name, year, competition, poule_id, teams, rankings):
    team_ids = [team["team_id"] for team in teams]
    return {
        "schema_version": "1.0",
        "retrieved_at": f"{year}-01-01T00:00:00Z",
        "source": "https://badminton.now/region/19",
        "region": {
            "region_id": 19,
            "name": "Bossche Badminton Federatie",
        },
        "season": {
            "name": season_name,
            "year": year,
        },
        "poules": [{
            "poule": {
                "poule_id": poule_id,
                "season_name": season_name,
                "competition": competition,
                "class": "Klasse 3",
                "source": f"https://badminton.now/poule/{poule_id}",
            },
            "teams": teams,
            "matches": [],
            "standings": [],
            "rankings": rankings,
            "match_details": [],
            "warnings": [],
        }],
    }


class PlayerProfileBuildTests(unittest.TestCase):
    def _write_documents(self, output_dir, documents):
        for document in documents:
            season = document["season"]
            path = output_dir / str(season["year"]) / (
                season["name"].replace(" ", "_") + ".json"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document), encoding="utf-8")

    def test_builds_one_normalized_profile_per_player_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "output"
            older = _season_document(
                "voorjaar 2019",
                2019,
                "Jeugd",
                100,
                [
                    {"team_id": 20, "name": "ABC 4"},
                    {"team_id": 21, "name": "Other 1"},
                ],
                [
                    _ranking(1, "Previous Name", 20, "ABC 4"),
                    _ranking(9, "Historic Only Player", 21, "Other 1"),
                ],
            )
            current = _season_document(
                "najaar 2026",
                2026,
                "Senioren",
                200,
                [
                    {"team_id": 10, "name": "ABC 3"},
                    {"team_id": 11, "name": "Other 2"},
                ],
                [
                    _ranking(1, "Current Name", 10, "ABC 3"),
                    _ranking(2, "Second Player", 10, "ABC 3"),
                    _ranking(8, "Other Current Player", 11, "Other 2"),
                ],
            )
            self._write_documents(output_dir, [older, current])

            result = build_player_profile_document(output_dir)

            profiles = {profile["player_id"]: profile for profile in result["players"]}
            self.assertEqual(set(profiles), {1, 2, 8, 9})
            player = profiles[1]
            self.assertEqual(player["full_name"], "Current Name")
            self.assertEqual(player["name_aliases"], ["Previous Name"])
            self.assertEqual(
                {group["group_id"] for group in player["group_history"]},
                {"jeugd", "senioren"},
            )
            self.assertEqual(result["schema_version"], "2.0")
            self.assertEqual(len(result["seasons"]), 2)

    def test_appearance_uses_only_entity_references_and_ranking_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "output"
            current = _season_document(
                "najaar 2026",
                2026,
                "Senioren",
                200,
                [{"team_id": 10, "name": "ABC 3"}],
                [_ranking(1, "Player One", 10, "ABC 3")],
            )
            self._write_documents(output_dir, [current])

            result = build_player_profile_document(output_dir)
            appearance = result["players"][0]["group_history"][0]["appearances"][0]

            self.assertEqual(set(appearance), {"poule_id", "team_id", "ranking"})
            self.assertEqual(
                set(appearance["ranking"]),
                {
                    "played",
                    "wins",
                    "win_pct",
                    "rating",
                    "prev_rating",
                    "anonymous",
                    "substitute",
                    "own_team",
                },
            )
            self.assertNotIn("full_name", appearance)
            self.assertNotIn("group_name", appearance)
            self.assertNotIn("season_name", appearance)
            self.assertNotIn("team_name", appearance)
            self.assertEqual(result["teams"], [{"team_id": 10, "name": "ABC 3"}])
            self.assertEqual(result["groups"], [{"group_id": "senioren", "name": "Senioren"}])

    def test_rejects_duplicate_ranking_for_player_and_poule(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "output"
            current = _season_document(
                "najaar 2026",
                2026,
                "Senioren",
                200,
                [{"team_id": 10, "name": "ABC 3"}],
                [
                    _ranking(1, "Player One", 10, "ABC 3"),
                    _ranking(1, "Player One", 10, "ABC 3"),
                ],
            )
            self._write_documents(output_dir, [current])

            with self.assertRaisesRegex(ProfileBuildError, "Duplicate ranking"):
                build_player_profile_document(output_dir)

    def test_rejects_conflicting_team_names_for_same_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "output"
            spring = _season_document(
                "voorjaar 2019",
                2019,
                "Senioren",
                100,
                [{"team_id": 10, "name": "ABC 3"}],
                [_ranking(1, "Player One", 10, "ABC 3")],
            )
            fall = _season_document(
                "najaar 2026",
                2026,
                "Senioren",
                200,
                [{"team_id": 10, "name": "ABC Three"}],
                [_ranking(1, "Player One", 10, "ABC Three")],
            )
            self._write_documents(output_dir, [spring, fall])

            with self.assertRaisesRegex(ProfileBuildError, "conflicting names"):
                build_player_profile_document(output_dir)


if __name__ == "__main__":
    unittest.main()
