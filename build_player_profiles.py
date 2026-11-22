#!/usr/bin/env python3
"""Build normalized player profiles from local Badminton NOW season JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REGION_ID = 19
EARLIEST_YEAR = 2019
LATEST_YEAR = 2026
PLAYER_RANKING_FIELDS = (
    "played",
    "wins",
    "win_pct",
    "rating",
    "prev_rating",
    "anonymous",
    "substitute",
    "own_team",
)


class ProfileBuildError(RuntimeError):
    """Raised when local season data cannot safely produce a profile export."""


def _read_season_documents(output_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    paths = sorted(output_dir.glob("[0-9][0-9][0-9][0-9]/*.json"))
    if not paths:
        raise ProfileBuildError(f"No season JSON files found under {output_dir}.")

    documents: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProfileBuildError(f"Could not read season JSON {path}: {error}") from error
        if not isinstance(document, dict):
            raise ProfileBuildError(f"Season JSON {path} is not an object.")
        if document.get("region", {}).get("region_id") != REGION_ID:
            raise ProfileBuildError(f"Season JSON {path} is not for region {REGION_ID}.")
        if not isinstance(document.get("poules"), list):
            raise ProfileBuildError(f"Season JSON {path} has no poules array.")
        documents.append((path, document))
    return documents


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")
    if not slug:
        raise ProfileBuildError(f"Cannot create a stable ID from {value!r}.")
    return slug


def _season_sort_key(season: dict[str, Any]) -> tuple[int, int]:
    name = str(season.get("name") or "").casefold()
    half_year_order = 0 if name.startswith("voorjaar") else 1
    return int(season["year"]), half_year_order


def _source_file(path: Path, output_dir: Path) -> str:
    return path.relative_to(output_dir.parent).as_posix()


def _record_entity(
    entities: dict[int, str],
    entity_id: Any,
    name: Any,
    entity_type: str,
) -> None:
    if entity_id is None:
        return
    if isinstance(entity_id, bool) or not isinstance(entity_id, int):
        raise ProfileBuildError(f"{entity_type} ID must be an integer: {entity_id!r}.")
    if not isinstance(name, str) or not name.strip():
        raise ProfileBuildError(f"{entity_type} {entity_id} has no usable name.")
    normalized_name = name.strip()
    existing = entities.get(entity_id)
    if existing is not None and existing != normalized_name:
        raise ProfileBuildError(
            f"{entity_type} ID {entity_id} has conflicting names: "
            f"{existing!r} and {normalized_name!r}."
        )
    entities[entity_id] = normalized_name


def _ranking_snapshot(ranking: dict[str, Any]) -> dict[str, Any]:
    return {
        field: ranking.get(field)
        for field in PLAYER_RANKING_FIELDS
    }


def _appearance_sort_key(
    appearance: dict[str, Any],
    poules: dict[int, dict[str, Any]],
    seasons: dict[str, dict[str, Any]],
) -> tuple[int, int, str, str, int]:
    poule = poules[appearance["poule_id"]]
    season = seasons[poule["season_id"]]
    year, half_year_order = _season_sort_key(season)
    return (
        year,
        half_year_order,
        poule["group_id"],
        (poule["class"] or "").casefold(),
        appearance["poule_id"],
    )


def build_player_profile_document(output_dir: Path) -> dict[str, Any]:
    documents = _read_season_documents(output_dir)
    region_values = {
        (
            document["region"].get("region_id"),
            document["region"].get("name"),
        )
        for _, document in documents
    }
    if len(region_values) != 1:
        raise ProfileBuildError("Season files have inconsistent region metadata.")
    region_id, region_name = next(iter(region_values))
    if not isinstance(region_name, str) or not region_name.strip():
        raise ProfileBuildError("Season files have no region name.")

    seasons: dict[str, dict[str, Any]] = {}
    groups: dict[str, str] = {}
    teams: dict[int, str] = {}
    poules: dict[int, dict[str, Any]] = {}
    players: dict[int, dict[str, Any]] = {}
    appearance_keys: set[tuple[int, int]] = set()

    for path, document in documents:
        source_season = document.get("season")
        if not isinstance(source_season, dict):
            raise ProfileBuildError(f"Season metadata is invalid in {path}.")
        season_name = source_season.get("name")
        season_year = source_season.get("year")
        if not isinstance(season_name, str) or not season_name.strip():
            raise ProfileBuildError(f"Season name is missing in {path}.")
        if (
            isinstance(season_year, bool)
            or not isinstance(season_year, int)
            or not EARLIEST_YEAR <= season_year <= LATEST_YEAR
        ):
            raise ProfileBuildError(f"Season year is out of range in {path}.")
        season_id = _slug(season_name)
        season_record = {
            "season_id": season_id,
            "name": season_name,
            "year": season_year,
            "retrieved_at": document.get("retrieved_at"),
            "source_file": _source_file(path, output_dir),
        }
        existing_season = seasons.get(season_id)
        if existing_season is not None and existing_season != season_record:
            raise ProfileBuildError(f"Season ID {season_id!r} is not unique.")
        seasons[season_id] = season_record

        for poule_entry in document["poules"]:
            if not isinstance(poule_entry, dict) or not isinstance(
                poule_entry.get("poule"), dict
            ):
                raise ProfileBuildError(f"A poule entry is invalid in {path}.")
            source_poule = poule_entry["poule"]
            poule_id = source_poule.get("poule_id")
            if isinstance(poule_id, bool) or not isinstance(poule_id, int):
                raise ProfileBuildError(f"A poule has an invalid ID in {path}.")
            group_name = source_poule.get("competition")
            if not isinstance(group_name, str) or not group_name.strip():
                raise ProfileBuildError(f"Poule {poule_id} has no competition group.")
            group_name = group_name.strip()
            group_id = _slug(group_name)
            existing_group = groups.get(group_id)
            if existing_group is not None and existing_group != group_name:
                raise ProfileBuildError(f"Group ID {group_id!r} is not unique.")
            groups[group_id] = group_name

            team_ids: set[int] = set()
            for team in poule_entry.get("teams", []):
                if not isinstance(team, dict):
                    raise ProfileBuildError(f"Poule {poule_id} contains an invalid team.")
                team_id = team.get("team_id")
                if team_id is None:
                    continue
                _record_entity(teams, team_id, team.get("name"), "Team")
                team_ids.add(team_id)

            poule_record = {
                "poule_id": poule_id,
                "season_id": season_id,
                "group_id": group_id,
                "class": source_poule.get("class"),
                "source": source_poule.get("source"),
                "team_ids": sorted(team_ids),
            }
            existing_poule = poules.get(poule_id)
            if existing_poule is not None and existing_poule != poule_record:
                raise ProfileBuildError(
                    f"Poule ID {poule_id} has conflicting metadata across source files."
                )
            poules[poule_id] = poule_record

            rankings = poule_entry.get("rankings")
            if not isinstance(rankings, list):
                raise ProfileBuildError(f"Poule {poule_id} has no rankings array.")
            for ranking_index, ranking in enumerate(rankings):
                if not isinstance(ranking, dict):
                    raise ProfileBuildError(
                        f"Poule {poule_id} ranking {ranking_index} is not an object."
                    )
                player_id = ranking.get("player_id")
                if isinstance(player_id, bool) or not isinstance(player_id, int):
                    raise ProfileBuildError(
                        f"Poule {poule_id} ranking {ranking_index} has no valid player ID."
                    )
                full_name = ranking.get("full_name")
                if not isinstance(full_name, str) or not full_name.strip():
                    raise ProfileBuildError(
                        f"Player {player_id} in poule {poule_id} has no name."
                    )
                full_name = full_name.strip()
                team_id = ranking.get("team_id")
                if team_id is not None:
                    _record_entity(teams, team_id, ranking.get("team_name"), "Team")
                    team_ids.add(team_id)
                    if team_id not in poule_record["team_ids"]:
                        raise ProfileBuildError(
                            f"Player {player_id} references team {team_id}, which is not "
                            f"listed in poule {poule_id}."
                        )

                appearance_key = (player_id, poule_id)
                if appearance_key in appearance_keys:
                    raise ProfileBuildError(
                        f"Duplicate ranking for player {player_id} in poule {poule_id}."
                    )
                appearance_keys.add(appearance_key)

                player = players.setdefault(
                    player_id,
                    {
                        "player_id": player_id,
                        "names": set(),
                        "names_by_season": defaultdict(set),
                        "appearances_by_group": defaultdict(list),
                    },
                )
                player["names"].add(full_name)
                player["names_by_season"][season_id].add(full_name)
                player["appearances_by_group"][group_id].append({
                    "poule_id": poule_id,
                    "team_id": team_id,
                    "ranking": _ranking_snapshot(ranking),
                })

    if not players:
        raise ProfileBuildError("No player ranking entries were found in source files.")

    ordered_seasons = sorted(seasons.values(), key=_season_sort_key)
    season_by_id = {season["season_id"]: season for season in ordered_seasons}
    ordered_groups = [
        {"group_id": group_id, "name": group_name}
        for group_id, group_name in sorted(
            groups.items(),
            key=lambda item: item[1].casefold(),
        )
    ]
    ordered_poules = sorted(
        poules.values(),
        key=lambda poule: (
            _season_sort_key(season_by_id[poule["season_id"]]),
            poule["group_id"],
            (poule["class"] or "").casefold(),
            poule["poule_id"],
        ),
    )

    profiles: list[dict[str, Any]] = []
    for player_id, player in players.items():
        names: set[str] = player["names"]
        newest_records = [
            appearance
            for appearances in player["appearances_by_group"].values()
            for appearance in appearances
        ]
        latest_season_key = max(
            _appearance_sort_key(appearance, poules, season_by_id)[:2]
            for appearance in newest_records
        )
        latest_season_ids = {
            poules[appearance["poule_id"]]["season_id"]
            for appearance in newest_records
            if _appearance_sort_key(appearance, poules, season_by_id)[:2]
            == latest_season_key
        }
        latest_names = {
            name
            for season_id in latest_season_ids
            for name in player["names_by_season"][season_id]
        }
        if len(latest_names) > 1:
            raise ProfileBuildError(
                f"Player {player_id} has ambiguous names in the latest season."
            )
        full_name = next(iter(latest_names))
        groups_history = []
        for group_id, appearances in player["appearances_by_group"].items():
            groups_history.append({
                "group_id": group_id,
                "appearances": sorted(
                    appearances,
                    key=lambda appearance: _appearance_sort_key(
                        appearance,
                        poules,
                        season_by_id,
                    ),
                ),
            })
        profiles.append({
            "player_id": player_id,
            "full_name": full_name,
            "name_aliases": sorted(names - {full_name}, key=str.casefold),
            "group_history": sorted(
                groups_history,
                key=lambda group: group["group_id"],
            ),
        })
    profiles.sort(key=lambda player: (
        player["full_name"].casefold(),
        player["player_id"],
    ))

    first_season = ordered_seasons[0]
    last_season = ordered_seasons[-1]
    return {
        "schema_version": "2.0",
        "generated_at": (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        ),
        "scope": {
            "region": {
                "region_id": region_id,
                "name": region_name,
            },
            "history_range": {
                "from_season_id": first_season["season_id"],
                "through_season_id": last_season["season_id"],
            },
            "player_population": "all_unique_player_ids_with_a_ranking_record_included_seasons",
        },
        "seasons": ordered_seasons,
        "groups": ordered_groups,
        "teams": [
            {"team_id": team_id, "name": name}
            for team_id, name in sorted(teams.items())
        ],
        "poules": ordered_poules,
        "players": profiles,
    }


def write_player_profile(output_dir: Path, output_file: Path) -> dict[str, Any]:
    document = build_player_profile_document(output_dir)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_file.with_suffix(output_file.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    temporary.replace(output_file)
    return document


def _build_parser() -> argparse.ArgumentParser:
    default_output_dir = Path(__file__).resolve().parent / "output"
    parser = argparse.ArgumentParser(
        description=(
            "Build deduplicated player profiles from local season JSON only; "
            "no website requests are made."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory containing year subfolders with season JSON files.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=default_output_dir / "player_profile.json",
        help="Profile JSON destination (default: output/player_profile.json).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        document = write_player_profile(args.output_dir, args.output_file)
    except ProfileBuildError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        f"Wrote {len(document['players'])} unique player profiles from "
        f"{len(document['seasons'])} seasons to {args.output_file}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
