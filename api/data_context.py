from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DataDirectoryError(RuntimeError):
    """Raised when the local season/profile exports cannot be read."""


@dataclass(frozen=True)
class RetrievedContext:
    text: str
    sources: list[str]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_marks.casefold()).strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DataDirectoryError(f"Required local data file is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise DataDirectoryError(f"Local data file is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise DataDirectoryError(f"Local data file must contain a JSON object: {path}")
    return value


class JsonDataContext:
    def __init__(
        self,
        profile: dict[str, Any],
        season_documents: list[tuple[str, dict[str, Any]]],
    ) -> None:
        self.profile = profile
        self.players = {
            player["player_id"]: player
            for player in profile.get("players", [])
            if isinstance(player, dict) and isinstance(player.get("player_id"), int)
        }
        self.groups = {
            group["group_id"]: group
            for group in profile.get("groups", [])
            if isinstance(group, dict) and isinstance(group.get("group_id"), str)
        }
        self.seasons = {
            season["season_id"]: season
            for season in profile.get("seasons", [])
            if isinstance(season, dict) and isinstance(season.get("season_id"), str)
        }
        self.teams = {
            team["team_id"]: team
            for team in profile.get("teams", [])
            if isinstance(team, dict) and isinstance(team.get("team_id"), int)
        }
        self.poules = {
            poule["poule_id"]: poule
            for poule in profile.get("poules", [])
            if isinstance(poule, dict) and isinstance(poule.get("poule_id"), int)
        }
        self.season_documents = season_documents
        self.poules_by_id: dict[int, tuple[str, dict[str, Any]]] = {}
        self.team_names: set[str] = set()
        for source_file, document in season_documents:
            for poule in document.get("poules", []):
                if not isinstance(poule, dict):
                    continue
                poule_info = poule.get("poule", {})
                if isinstance(poule_info, dict) and isinstance(poule_info.get("poule_id"), int):
                    self.poules_by_id[poule_info["poule_id"]] = (source_file, poule)
                for team in poule.get("teams", []):
                    if isinstance(team, dict) and isinstance(team.get("name"), str):
                        self.team_names.add(team["name"])

    @classmethod
    def load(cls, output_dir: Path) -> JsonDataContext:
        profile_path = output_dir / "player_profile.json"
        profile = _read_json(profile_path)
        if profile.get("schema_version") != "2.0":
            raise DataDirectoryError(
                "The local player profile must use schema version 2.0. "
                "Regenerate it with build_player_profiles.py."
            )
        if not isinstance(profile.get("players"), list):
            raise DataDirectoryError("The local player profile has no players array.")

        season_documents: list[tuple[str, dict[str, Any]]] = []
        for path in sorted(output_dir.glob("[0-9][0-9][0-9][0-9]/*.json")):
            document = _read_json(path)
            if not isinstance(document.get("poules"), list):
                raise DataDirectoryError(f"Season file has no poules array: {path}")
            season_documents.append(
                (path.relative_to(output_dir.parent).as_posix(), document)
            )
        if not season_documents:
            raise DataDirectoryError(
                f"No season JSON files were found below {output_dir}."
            )
        return cls(profile, season_documents)

    def build(self, question: str, selected_player_id: int | None) -> RetrievedContext:
        normalized_question = _normalize(question)
        matched_players = self._find_players(normalized_question, selected_player_id)
        sections: list[str] = []
        sources: list[str] = []

        for player in matched_players[:3]:
            section, player_sources = self._player_section(player, normalized_question)
            if section:
                sections.append(section)
                sources.extend(player_sources)

        team_sections, team_sources = self._team_sections(normalized_question)
        sections.extend(team_sections)
        sources.extend(team_sources)

        if not sections:
            return RetrievedContext(
                text=(
                    "No matching player, team, poule, or season records were found "
                    "in the local JSON exports. Do not answer with guessed facts."
                ),
                sources=[],
            )

        unique_sources = list(dict.fromkeys(sources))
        context = "\n\n".join(sections)
        if len(context) > 24_000:
            context = context[:24_000] + "\n[Context shortened to fit the local chat request.]"
        return RetrievedContext(text=context, sources=unique_sources)

    def _find_players(
        self,
        normalized_question: str,
        selected_player_id: int | None,
    ) -> list[dict[str, Any]]:
        candidates: dict[int, dict[str, Any]] = {}
        if selected_player_id is not None:
            player = self.players.get(selected_player_id)
            if player is None:
                raise ValueError(f"Player ID {selected_player_id} is not in the local profile.")
            candidates[selected_player_id] = player

        for numeric_id in re.findall(r"(?<!\d)\d{5,}(?!\d)", normalized_question):
            player_id = int(numeric_id)
            player = self.players.get(player_id)
            if player is not None:
                candidates[player_id] = player

        for player_id, player in self.players.items():
            names = [player.get("full_name", ""), *player.get("name_aliases", [])]
            for name in names:
                if not isinstance(name, str):
                    continue
                normalized_name = _normalize(name)
                if len(normalized_name) >= 4 and normalized_name in normalized_question:
                    candidates[player_id] = player
                    break

        return list(candidates.values())

    def _player_section(
        self,
        player: dict[str, Any],
        normalized_question: str,
    ) -> tuple[str, list[str]]:
        player_id = player["player_id"]
        rows: list[dict[str, Any]] = []
        group_filter = next(
            (
                group_id
                for group_id, group in self.groups.items()
                if _normalize(group.get("name", "")) in normalized_question
            ),
            None,
        )
        year_matches = {int(year) for year in re.findall(r"\b20\d{2}\b", normalized_question)}
        history_question = any(
            word in normalized_question
            for word in ("history", "career", "since", "over time", "trend", "all seasons")
        )

        for group_history in player.get("group_history", []):
            group_id = group_history.get("group_id")
            if group_filter and group_id != group_filter:
                continue
            group = self.groups.get(group_id, {})
            for appearance in group_history.get("appearances", []):
                poule_id = appearance.get("poule_id")
                poule = self.poules.get(poule_id, {})
                season = self.seasons.get(poule.get("season_id"), {})
                year = season.get("year")
                if year_matches and year not in year_matches:
                    continue
                rows.append({
                    "season": season.get("name"),
                    "year": season.get("year", 0),
                    "group": group.get("name"),
                    "class": poule.get("class"),
                    "poule_id": poule_id,
                    "team": self.teams.get(appearance.get("team_id"), {}).get("name"),
                    "ranking": appearance.get("ranking", {}),
                    "source_file": season.get("source_file"),
                })

        rows.sort(
            key=lambda row: (
                row.get("year", 0),
                1 if _normalize(row.get("season") or "").startswith("najaar") else 0,
                row.get("poule_id") or 0,
            )
        )
        if not history_question and not year_matches:
            rows = rows[-6:]
        else:
            rows = rows[-24:]

        if not rows:
            return "", []

        lines = [
            f"Player: {player.get('full_name')} (player_id={player_id}).",
            f"Aliases: {', '.join(player.get('name_aliases', [])) or 'none listed'}.",
            "Ranking appearances (snapshots, not match-by-match results):",
        ]
        sources = ["output/player_profile.json"]
        for row in rows:
            ranking = row["ranking"]
            lines.append(
                "- "
                f"{row.get('season')} / {row.get('group')} / "
                f"{row.get('class') or 'unclassified'} / {row.get('team') or 'team unknown'} "
                f"/ poule {row.get('poule_id')}: "
                f"played={ranking.get('played')}, wins={ranking.get('wins')}, "
                f"win_pct={ranking.get('win_pct')}, rating={ranking.get('rating')} "
                f"[source: {row.get('source_file')}, player_profile.json]."
            )
            source_file = row.get("source_file")
            if source_file:
                sources.append(source_file)

        if "match" in normalized_question or "rubber" in normalized_question:
            lines.append(
                "Individual player match/rubber/set results are not present in the profile JSON."
            )
        return "\n".join(lines), sources

    def _team_sections(
        self,
        normalized_question: str,
    ) -> tuple[list[str], list[str]]:
        matched_team_names = [
            name for name in self.team_names
            if len(_normalize(name)) >= 3 and _normalize(name) in normalized_question
        ]
        if not matched_team_names:
            return [], []

        year_matches = {int(year) for year in re.findall(r"\b20\d{2}\b", normalized_question)}
        history_question = any(
            word in normalized_question
            for word in ("history", "career", "since", "over time", "all seasons")
        )
        relevant: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for source_file, document in self.season_documents:
            season = document.get("season", {})
            if year_matches and season.get("year") not in year_matches:
                continue
            for poule_entry in document.get("poules", []):
                poule = poule_entry.get("poule", {})
                teams = poule_entry.get("teams", [])
                if any(
                    team.get("name") in matched_team_names
                    for team in teams
                    if isinstance(team, dict)
                ):
                    relevant.append((source_file, document, poule_entry))

        relevant.sort(
            key=lambda row: (
                row[1].get("season", {}).get("year", 0),
                row[1].get("season", {}).get("name", ""),
            )
        )
        if not history_question and not year_matches:
            latest_season = max(
                (
                    row[1].get("season", {}).get("year", 0),
                    row[1].get("season", {}).get("name", ""),
                )
                for row in relevant
            ) if relevant else None
            relevant = [
                row
                for row in relevant
                if (row[1].get("season", {}).get("year", 0), row[1].get("season", {}).get("name", ""))
                == latest_season
            ]
        else:
            relevant = relevant[-12:]

        sections: list[str] = []
        sources: list[str] = []
        for source_file, document, poule_entry in relevant:
            poule = poule_entry.get("poule", {})
            team_names = [
                team.get("name")
                for team in poule_entry.get("teams", [])
                if isinstance(team, dict)
            ]
            standings = [
                {
                    "team": row.get("team_name"),
                    "played": row.get("played"),
                    "points": row.get("points"),
                }
                for row in poule_entry.get("standings", [])
            ]
            matches = [
                {
                    "match_number": row.get("match_number"),
                    "play_time": row.get("play_time"),
                    "team1": row.get("team1", {}).get("name"),
                    "team2": row.get("team2", {}).get("name"),
                    "score1": row.get("score1"),
                    "score2": row.get("score2"),
                }
                for row in poule_entry.get("matches", [])
                if any(
                    team_name in matched_team_names
                    for team_name in (
                        row.get("team1", {}).get("name"),
                        row.get("team2", {}).get("name"),
                    )
                )
            ][-12:]
            section = {
                "season": document.get("season", {}).get("name"),
                "group": poule.get("competition"),
                "class": poule.get("class"),
                "poule_id": poule.get("poule_id"),
                "source_file": source_file,
                "teams": team_names,
                "standings": standings,
                "matches": matches,
            }
            sections.append(
                "Team/poule records:\n"
                + json.dumps(section, ensure_ascii=False, separators=(",", ":"))
            )
            sources.append(
                f"{source_file} (poule {poule.get('poule_id')})"
            )
        return sections, sources
