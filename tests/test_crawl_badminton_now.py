import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from crawl_badminton_now import (
    CrawlError,
    DataShapeError,
    GroupCandidate,
    PouleCandidate,
    SeasonCandidate,
    _load_robots_parser,
    discover_groups,
    discover_poules,
    discover_seasons,
    normalize_poule,
    season_filename,
    write_season_outputs,
)


class DiscoveryTests(unittest.TestCase):
    def test_discovers_available_seasons_through_spring_2019(self):
        payloads = [{
            "seasons": [
                {"id": 1, "name": "najaar 2027"},
                {"id": 2, "name": "najaar 2026"},
                {"id": 3, "name": "voorjaar 2026"},
                {"id": 4, "name": "voorjaar 2020"},
                {"id": 5, "name": "najaar 2019"},
                {"id": 6, "name": "voorjaar 2019"},
                {"id": 7, "name": "najaar 2018"},
            ]
        }]

        seasons = discover_seasons(payloads)

        self.assertEqual(
            seasons,
            [
                SeasonCandidate(2, "najaar 2026"),
                SeasonCandidate(3, "voorjaar 2026"),
                SeasonCandidate(4, "voorjaar 2020"),
                SeasonCandidate(5, "najaar 2019"),
                SeasonCandidate(6, "voorjaar 2019"),
            ],
        )

    def test_requires_the_requested_cutoff_season(self):
        with self.assertRaisesRegex(CrawlError, "cutoff season"):
            discover_seasons([{"seasons": [{"id": 1, "name": "najaar 2026"}]}])

    def test_discovers_groups_and_poules_from_page_payloads(self):
        season = SeasonCandidate(52698, "najaar 2026")
        groups = discover_groups(
            [{"groups": [{"id": 53195, "name": "Senioren"}]}],
            season,
        )
        self.assertEqual(groups, [GroupCandidate(53195, "Senioren")])
        self.assertEqual(
            discover_poules(
                [{"poules": [{"pouleid": 5022253, "poulename": "Klasse 3"}]}],
                season,
                groups[0],
            ),
            [PouleCandidate(5022253, "najaar 2026")],
        )


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.candidate = PouleCandidate(5022253, "najaar 2026")
        self.match_payloads = [{
            "pouleid": 5022253,
            "seasonname": "najaar 2026",
            "groupname": "Senioren",
            "poulename": "Klasse 3",
            "matches": [
                {
                    "id": "9001",
                    "matchnr": "1201",
                    "playtime": "2026-11-20 19:00",
                    "team1id": "11",
                    "team1name": "BCSV 2",
                    "team2id": "12",
                    "team2name": "ABC 3",
                    "score1": "7",
                    "score2": "9",
                    "numsets": "8",
                    "status": "completed",
                    "canceled": "0",
                    "postponed": False,
                    "remark": "",
                    "locationid": "3",
                    "matchtypeid": "2",
                    "hasissue": 0,
                    "period": "najaar",
                },
                {
                    "id": "9002",
                    "matchnr": None,
                    "team1id": "11",
                    "team1name": "BCSV 2",
                    "team2id": "12",
                    "team2name": "ABC 3",
                    "score1": None,
                    "score2": None,
                    "numsets": "0",
                },
            ],
        }]
        self.standings_payloads = [{
            "standings": [
                {
                    "teamid": "11",
                    "teamname": "BCSV 2",
                    "nplayed": "1",
                    "points": "7",
                    "withdrawn": 0,
                    "teamrating": "1.25",
                    "startpoints": "0",
                    "unfinpoints": "0",
                },
                {
                    "teamid": "12",
                    "teamname": "ABC 3",
                    "nplayed": "1",
                    "points": "9",
                    "withdrawn": False,
                    "teamrating": "2",
                    "startpoints": "0",
                    "unfinpoints": "0",
                },
            ]
        }]
        self.ranking_payloads = [{
            "results": [
                {
                    "id": "6012722",
                    "fullname": "Example Player",
                    "teamid": "12",
                    "teamname": "ABC 3",
                    "nplayed": "26",
                    "wins": "11",
                    "pct": "42.308",
                    "rating": "7.1",
                    "prevrating": "6.9",
                    "anonymous": "0",
                    "sub": "0",
                    "ownteam": "1",
                }
            ]
        }]

    def test_normalizes_tabs_and_keeps_unplayed_match_scores_null(self):
        poule = normalize_poule(
            self.candidate,
            self.match_payloads,
            self.standings_payloads,
            self.ranking_payloads,
        )

        self.assertEqual(poule["poule"]["competition"], "Senioren")
        self.assertEqual(poule["poule"]["class"], "Klasse 3")
        self.assertEqual(poule["matches"][0]["match_id"], 9001)
        self.assertEqual(poule["matches"][0]["score1"], 7)
        self.assertIsNone(poule["matches"][1]["score1"])
        self.assertEqual(poule["rankings"][0]["player_id"], 6012722)
        self.assertEqual(poule["rankings"][0]["win_pct"], 42.308)
        self.assertEqual(poule["match_details"], [])
        self.assertEqual(
            [warning["code"] for warning in poule["warnings"]],
            ["MATCH_DETAILS_PENDING_PHASE_0"],
        )

    def test_rejects_mismatched_poule_payload(self):
        payloads = [{"pouleid": 999, "matches": []}]
        with self.assertRaisesRegex(RuntimeError, "belongs to poule 999"):
            normalize_poule(
                self.candidate,
                payloads,
                self.standings_payloads,
                self.ranking_payloads,
            )

    def test_rejects_non_object_collection_entries(self):
        payloads = [dict(self.match_payloads[0], matches=[None])]
        with self.assertRaisesRegex(DataShapeError, r"matches\[0\]"):
            normalize_poule(
                self.candidate,
                payloads,
                self.standings_payloads,
                self.ranking_payloads,
            )

    def test_prefers_discovered_season_name_over_year_only_payload(self):
        payloads = [dict(self.match_payloads[0])]
        payloads[0].pop("seasonname")
        payloads[0]["year"] = 2026

        poule = normalize_poule(
            self.candidate,
            payloads,
            self.standings_payloads,
            self.ranking_payloads,
        )

        self.assertEqual(poule["poule"]["season_name"], "najaar 2026")

    def test_warns_when_match_team_is_missing_from_standings(self):
        standings = [{
            "standings": [self.standings_payloads[0]["standings"][0]]
        }]

        poule = normalize_poule(
            self.candidate,
            self.match_payloads,
            standings,
            self.ranking_payloads,
        )

        self.assertIn(
            "MATCH_TEAM_NOT_IN_STANDINGS",
            [warning["code"] for warning in poule["warnings"]],
        )

    def test_accepts_score_totals_for_six_or_eight_event_formats(self):
        matches = [dict(match) for match in self.match_payloads[0]["matches"]]
        matches[0].update(numsets="6", score1="7", score2="5")
        matches[1].update(numsets="6", score1="16", score2="0")
        payloads = [dict(self.match_payloads[0], matches=matches)]

        poule = normalize_poule(
            self.candidate,
            payloads,
            self.standings_payloads,
            self.ranking_payloads,
        )

        self.assertNotIn(
            "TEAM_SCORE_TOTAL",
            [warning["code"] for warning in poule["warnings"]],
        )

    def test_warns_on_score_total_outside_supported_formats(self):
        matches = [dict(match) for match in self.match_payloads[0]["matches"]]
        matches[0].update(numsets="6", score1="7", score2="4")
        payloads = [dict(self.match_payloads[0], matches=matches)]

        poule = normalize_poule(
            self.candidate,
            payloads,
            self.standings_payloads,
            self.ranking_payloads,
        )

        self.assertIn(
            "TEAM_SCORE_TOTAL",
            [warning["code"] for warning in poule["warnings"]],
        )


class OutputTests(unittest.TestCase):
    def test_season_filename_and_output_shape(self):
        self.assertEqual(season_filename("najaar 2026"), "najaar_2026.json")
        poule = {
            "poule": {
                "poule_id": 5022253,
                "season_name": "najaar 2026",
                "competition": "Senioren",
                "class": "Klasse 3",
            },
            "teams": [],
            "matches": [],
            "standings": [],
            "rankings": [],
            "match_details": [],
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_season_outputs([poule], Path(temporary))
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].relative_to(temporary).as_posix(), "2026/najaar_2026.json")
            document = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual(document["region"]["region_id"], 19)
            self.assertEqual(document["season"], {"name": "najaar 2026", "year": 2026})
            self.assertEqual(document["poules"][0]["poule"]["poule_id"], 5022253)

    def test_writes_seasons_under_their_year_directories(self):
        template = {
            "poule": {
                "poule_id": 1,
                "season_name": "najaar 2026",
                "competition": None,
                "class": None,
            },
            "teams": [],
            "matches": [],
            "standings": [],
            "rankings": [],
            "match_details": [],
            "warnings": [],
        }
        historical = dict(template)
        historical["poule"] = dict(template["poule"], season_name="voorjaar 2019")

        with tempfile.TemporaryDirectory() as temporary:
            paths = write_season_outputs([template, historical], Path(temporary))
            relative_paths = {path.relative_to(temporary).as_posix() for path in paths}
            self.assertEqual(
                relative_paths,
                {"2019/voorjaar_2019.json", "2026/najaar_2026.json"},
            )

    def test_output_refuses_seasons_outside_requested_range(self):
        poule = {
            "poule": {"poule_id": 1, "season_name": "najaar 2018"},
            "teams": [],
            "matches": [],
            "standings": [],
            "rankings": [],
            "match_details": [],
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "out-of-range"):
                write_season_outputs([poule], Path(temporary))


class RobotsTests(unittest.TestCase):
    def test_rejects_html_robots_response_unless_overridden(self):
        html_response = BytesIO(b"<!DOCTYPE html><html><body>Badminton NOW</body></html>")
        with patch("crawl_badminton_now.urlopen", return_value=html_response):
            with self.assertRaisesRegex(CrawlError, "returned HTML"):
                _load_robots_parser(allow_unavailable=False)

        html_response = BytesIO(b"<!DOCTYPE html><html><body>Badminton NOW</body></html>")
        with patch("crawl_badminton_now.urlopen", return_value=html_response):
            self.assertIsNone(_load_robots_parser(allow_unavailable=True))


if __name__ == "__main__":
    unittest.main()
