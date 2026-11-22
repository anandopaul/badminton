#!/usr/bin/env python3
"""Browser-assisted Phase 1 proof of concept for Badminton NOW."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser


BASE_URL = "https://badminton.now"
REGION_ID = 19
REGION_URL = f"{BASE_URL}/region/{REGION_ID}"
REGION_NAME = "Bossche Badminton Federatie"
EARLIEST_SEASON_YEAR = 2019
LATEST_SEASON_YEAR = 2026
LAST_SEASON_NAME = "voorjaar 2019"
API_DELAY_SECONDS = 1.5
USER_AGENT = "BadmintonNowAnalysisPOC/1.0"
PAYLOADS_GLOBAL = "__badmintonNowPocPayloads"

CAPTURE_DECODED_PAYLOADS = r"""
(() => {
  const globalName = "__badmintonNowPocPayloads";
  const originalParse = JSON.parse.bind(JSON);
  const marker = /"(?:matches|standings|results|poules|poulelist|pouleid|poule_id|regionname|seasonname|team1id|fullname|rubbers)"\s*:/i;
  Object.defineProperty(window, globalName, {
    value: [],
    configurable: true
  });

  JSON.parse = function(text, reviver) {
    const parsed = originalParse(text, reviver);
    if (typeof text === "string" && marker.test(text) &&
        parsed !== null && typeof parsed === "object") {
      try {
        window[globalName].push(structuredClone(parsed));
      } catch {
        window[globalName].push(parsed);
      }
    }
    return parsed;
  };
})();
"""


class CrawlError(RuntimeError):
    """Raised when collection cannot safely or reliably continue."""


class DataShapeError(CrawlError):
    """Raised when a source value cannot be normalized without guessing."""


@dataclass(frozen=True)
class PouleCandidate:
    poule_id: int
    season_name: str


@dataclass(frozen=True)
class SeasonCandidate:
    season_id: int
    season_name: str


@dataclass(frozen=True)
class GroupCandidate:
    group_id: int
    name: str


class ApiRequestPacer:
    def __init__(self, interval_seconds: float = API_DELAY_SECONDS) -> None:
        self.interval_seconds = interval_seconds
        self.last_request: float | None = None

    def wait(self) -> None:
        now = time.monotonic()
        if self.last_request is not None:
            remaining = self.interval_seconds - (now - self.last_request)
            if remaining > 0:
                time.sleep(remaining)
        self.last_request = time.monotonic()


def _key_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _direct_value(record: Any, *aliases: str) -> Any:
    if not isinstance(record, dict):
        return None
    wanted = {_key_name(alias) for alias in aliases}
    for key, value in record.items():
        if _key_name(key) in wanted:
            return value
    return None


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _find_value(payloads: Iterable[Any], *aliases: str) -> Any:
    for payload in payloads:
        for record in _walk_dicts(payload):
            value = _direct_value(record, *aliases)
            if value is not None:
                return value
    return None


def _find_collection(payloads: Iterable[Any], *aliases: str) -> list[Any] | None:
    wanted = {_key_name(alias) for alias in aliases}
    for payload in payloads:
        for record in _walk_dicts(payload):
            for key, value in record.items():
                if _key_name(key) in wanted and isinstance(value, list):
                    return value
    return None


def _as_number(value: Any, field: str) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise DataShapeError(f"{field} was boolean, not a number")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace("%", "").replace(",", ".")
        try:
            number = float(text)
        except ValueError as error:
            raise DataShapeError(f"{field} was not numeric: {value!r}") from error
    if not math.isfinite(number):
        raise DataShapeError(f"{field} was not finite")
    if number.is_integer():
        return int(number)
    return number


def _as_int(value: Any, field: str) -> int | None:
    number = _as_number(value, field)
    if number is None:
        return None
    if not isinstance(number, int):
        raise DataShapeError(f"{field} was not an integer: {value!r}")
    return number


def _as_bool(value: Any, field: str) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value in (0, 1):
            return bool(value)
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "ja"}:
        return True
    if text in {"0", "false", "no", "nee"}:
        return False
    raise DataShapeError(f"{field} was not a recognizable boolean: {value!r}")


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _season_name_from_text(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value).strip(" \t\r\n-")
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if year_match is None:
        return None
    named_season = re.search(
        r"\b(voorjaar|najaar)\b[^\n,;|]{0,30}\b(20\d{2})\b",
        normalized,
        re.IGNORECASE,
    )
    if named_season:
        return f"{named_season.group(1).casefold()} {named_season.group(2)}"
    if re.fullmatch(rf"{year_match.group(1)}(?:\s+{year_match.group(1)})*", normalized):
        return year_match.group(1)
    return normalized


def _season_year(season_name: str) -> int:
    match = re.search(r"\b(20\d{2})\b", season_name)
    if match is None:
        raise CrawlError(f"Season name does not contain a year: {season_name!r}")
    return int(match.group(1))


def discover_seasons(payloads: Iterable[Any]) -> list[SeasonCandidate]:
    rows = _find_collection(payloads, "seasons")
    if rows is None:
        raise CrawlError("The region page did not expose a seasons collection.")

    candidates: list[SeasonCandidate] = []
    seen_names: set[str] = set()
    cutoff_found = False
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DataShapeError(f"seasons[{index}] was not an object.")
        name = _season_name_from_text(_as_text(_direct_value(row, "name")) or "")
        if name is None:
            continue
        year = _season_year(name)
        if year > LATEST_SEASON_YEAR:
            continue
        if year < EARLIEST_SEASON_YEAR:
            break
        season_id = _as_int(
            _direct_value(row, "id", "seasonid", "season_id"),
            f"seasons[{index}].id",
        )
        if season_id is None:
            raise DataShapeError(f"seasons[{index}] has no season ID.")
        if name in seen_names:
            raise CrawlError(f"The region page listed season {name!r} more than once.")
        candidates.append(SeasonCandidate(season_id, name))
        seen_names.add(name)
        if name == LAST_SEASON_NAME:
            cutoff_found = True
            break

    if not cutoff_found:
        raise CrawlError(
            f"The region page did not list the requested cutoff season "
            f"{LAST_SEASON_NAME!r}; no historical crawl was started."
        )
    return candidates


def discover_groups(
    payloads: Iterable[Any],
    season: SeasonCandidate,
) -> list[GroupCandidate]:
    rows = _find_collection(payloads, "groups")
    if rows is None:
        raise CrawlError(f"Season {season.season_name}: groups collection was not decoded.")

    groups: list[GroupCandidate] = []
    seen_ids: set[int] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DataShapeError(f"groups[{index}] was not an object.")
        group_id = _as_int(
            _direct_value(row, "id", "groupid", "group_id"),
            f"groups[{index}].id",
        )
        name = _as_text(_direct_value(row, "name", "groupname"))
        if group_id is None or name is None:
            raise DataShapeError(f"groups[{index}] is missing its ID or name.")
        if group_id in seen_ids:
            raise CrawlError(f"Season {season.season_name} repeats group ID {group_id}.")
        groups.append(GroupCandidate(group_id, name))
        seen_ids.add(group_id)
    return groups


def discover_poules(
    payloads: Iterable[Any],
    season: SeasonCandidate,
    group: GroupCandidate,
) -> list[PouleCandidate]:
    rows = _find_collection(payloads, "poules")
    if rows is None:
        raise CrawlError(
            f"Season {season.season_name}, group {group.name}: poules collection was not decoded."
        )

    candidates: list[PouleCandidate] = []
    seen_ids: set[int] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DataShapeError(f"poules[{index}] was not an object.")
        poule_id = _as_int(
            _direct_value(row, "pouleid", "poule_id"),
            f"poules[{index}].pouleid",
        )
        if poule_id is None:
            raise DataShapeError(f"poules[{index}] has no poule ID.")
        if poule_id in seen_ids:
            raise CrawlError(f"Group {group.name} repeats poule ID {poule_id}.")
        candidates.append(PouleCandidate(poule_id, season.season_name))
        seen_ids.add(poule_id)
    return candidates


def _normalize_match(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "match_id": _as_int(_direct_value(row, "id", "matchid", "match_id"), "match_id"),
        "match_number": _as_int(_direct_value(row, "matchnr", "match_number"), "match_number"),
        "play_time": _as_text(_direct_value(row, "playtime", "play_time")),
        "team1": {
            "team_id": _as_int(_direct_value(row, "team1id", "team1_id"), "team1_id"),
            "name": _as_text(_direct_value(row, "team1name", "team1_name")),
        },
        "team2": {
            "team_id": _as_int(_direct_value(row, "team2id", "team2_id"), "team2_id"),
            "name": _as_text(_direct_value(row, "team2name", "team2_name")),
        },
        "score1": _as_int(_direct_value(row, "score1"), "score1"),
        "score2": _as_int(_direct_value(row, "score2"), "score2"),
        "num_sets": _as_int(_direct_value(row, "numsets", "num_sets"), "num_sets"),
        "status": _direct_value(row, "status"),
        "canceled": _as_bool(_direct_value(row, "canceled"), "canceled"),
        "postponed": _as_bool(_direct_value(row, "postponed"), "postponed"),
        "remark": _as_text(_direct_value(row, "remark")),
        "location_id": _as_int(_direct_value(row, "locationid", "location_id"), "location_id"),
        "match_type_id": _as_int(_direct_value(row, "matchtypeid", "match_type_id"), "match_type_id"),
        "has_issue": _as_bool(_direct_value(row, "hasissue", "has_issue"), "has_issue"),
        "period": _direct_value(row, "period"),
    }


def _normalize_standing(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_id": _as_int(_direct_value(row, "teamid", "team_id"), "team_id"),
        "team_name": _as_text(_direct_value(row, "teamname", "team_name")),
        "played": _as_int(_direct_value(row, "nplayed", "played"), "played"),
        "points": _as_number(_direct_value(row, "points"), "points"),
        "withdrawn": _as_bool(_direct_value(row, "withdrawn"), "withdrawn"),
        "team_rating": _as_number(_direct_value(row, "teamrating", "team_rating"), "team_rating"),
        "start_points": _as_number(_direct_value(row, "startpoints", "start_points"), "start_points"),
        "unfinished_points": _as_number(
            _direct_value(row, "unfinpoints", "unfinished_points"), "unfinished_points"
        ),
    }


def _normalize_ranking(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "player_id": _as_int(_direct_value(row, "id", "playerid", "player_id"), "player_id"),
        "full_name": _as_text(_direct_value(row, "fullname", "full_name")),
        "team_id": _as_int(_direct_value(row, "teamid", "team_id"), "team_id"),
        "team_name": _as_text(_direct_value(row, "teamname", "team_name")),
        "played": _as_int(_direct_value(row, "nplayed", "played"), "played"),
        "wins": _as_int(_direct_value(row, "wins"), "wins"),
        "win_pct": _as_number(_direct_value(row, "pct", "win_pct"), "win_pct"),
        "rating": _as_number(_direct_value(row, "rating"), "rating"),
        "prev_rating": _as_number(_direct_value(row, "prevrating", "prev_rating"), "prev_rating"),
        "anonymous": _as_bool(_direct_value(row, "anonymous"), "anonymous"),
        "substitute": _as_bool(_direct_value(row, "sub", "substitute"), "substitute"),
        "own_team": _as_bool(_direct_value(row, "ownteam", "own_team"), "own_team"),
    }


def _normalize_rows(
    rows: list[Any],
    normalizer: Callable[[dict[str, Any]], dict[str, Any]],
    collection_name: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DataShapeError(
                f"{collection_name}[{index}] was not an object: {type(row).__name__}"
            )
        normalized.append(normalizer(row))
    return normalized


def _collect_teams(
    matches: list[dict[str, Any]],
    standings: list[dict[str, Any]],
    rankings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}

    def add(team_id: int | None, name: str | None) -> None:
        if team_id is None and name is None:
            return
        team = {"team_id": team_id, "name": name}
        if team_id is not None:
            existing = by_id.get(team_id)
            if existing and existing["name"] and name and existing["name"] != name:
                raise DataShapeError(
                    f"Team ID {team_id} was associated with conflicting names: "
                    f"{existing['name']!r} and {name!r}"
                )
            by_id[team_id] = team if existing is None or existing["name"] is None else existing
        elif name is not None:
            by_name.setdefault(name.casefold(), team)

    for match in matches:
        for side in ("team1", "team2"):
            add(match[side]["team_id"], match[side]["name"])
    for standing in standings:
        add(standing["team_id"], standing["team_name"])
    for ranking in rankings:
        add(ranking["team_id"], ranking["team_name"])

    return sorted(
        [*by_id.values(), *by_name.values()],
        key=lambda team: (team["name"] or "").casefold(),
    )


def _is_completed(match: dict[str, Any]) -> bool:
    return (
        match["score1"] is not None
        and match["score2"] is not None
        and match["canceled"] is not True
        and match["postponed"] is not True
    )


def validate_poule(
    matches: list[dict[str, Any]],
    standings: list[dict[str, Any]],
    rankings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    standing_team_ids = {
        standing["team_id"]
        for standing in standings
        if standing["team_id"] is not None
    }

    for match in matches:
        match_id = match["match_id"]
        for side in ("team1", "team2"):
            team_id = match[side]["team_id"]
            if team_id is None:
                warnings.append({
                    "code": "MATCH_TEAM_ID_MISSING",
                    "match_id": match_id,
                    "message": f"{side} has no team ID.",
                })
            elif team_id not in standing_team_ids:
                warnings.append({
                    "code": "MATCH_TEAM_NOT_IN_STANDINGS",
                    "match_id": match_id,
                    "message": f"{side} team ID {team_id} was not present in the standings.",
                })
        if _is_completed(match):
            expected_totals = {16}
            if match["num_sets"] is not None:
                expected_totals.add(match["num_sets"] * 2)
            actual_total = match["score1"] + match["score2"]
            if actual_total not in expected_totals:
                warnings.append({
                    "code": "TEAM_SCORE_TOTAL",
                    "match_id": match_id,
                    "message": (
                        f"Expected the two team scores to sum to one of "
                        f"{sorted(expected_totals)}, found {actual_total}."
                    ),
                })
        if _is_completed(match):
            warnings.append({
                "code": "MATCH_DETAILS_PENDING_PHASE_0",
                "match_id": match_id,
                "message": (
                    "The handover does not identify the match-detail request; "
                    "rubbers and set scores were not inferred."
                ),
            })

    for ranking in rankings:
        played = ranking["played"]
        wins = ranking["wins"]
        win_pct = ranking["win_pct"]
        if played and wins is not None and win_pct is not None:
            expected_pct = wins / played * 100
            if not math.isclose(expected_pct, win_pct, abs_tol=0.01):
                warnings.append({
                    "code": "RANKING_PERCENTAGE",
                    "match_id": None,
                    "message": (
                        f"Player {ranking['player_id']} reports {win_pct}% but "
                        f"wins/played is {expected_pct:.3f}%."
                    ),
                })
    return warnings


def normalize_poule(
    candidate: PouleCandidate,
    match_payloads: list[Any],
    standings_payloads: list[Any],
    ranking_payloads: list[Any],
) -> dict[str, Any]:
    match_rows = _find_collection(match_payloads, "matches")
    standings_rows = _find_collection(standings_payloads, "standings")
    ranking_rows = _find_collection(ranking_payloads, "results")
    if match_rows is None:
        raise CrawlError(f"Poule {candidate.poule_id}: matches payload was not decoded.")
    if standings_rows is None:
        raise CrawlError(f"Poule {candidate.poule_id}: standings payload was not decoded.")
    if ranking_rows is None:
        raise CrawlError(f"Poule {candidate.poule_id}: rankings payload was not decoded.")

    matches = _normalize_rows(match_rows, _normalize_match, "matches")
    standings = _normalize_rows(standings_rows, _normalize_standing, "standings")
    rankings = _normalize_rows(ranking_rows, _normalize_ranking, "results")
    teams = _collect_teams(matches, standings, rankings)

    payloads = [*match_payloads, *standings_payloads, *ranking_payloads]
    source_poule_id = _as_int(_find_value(payloads, "pouleid", "poule_id"), "poule_id")
    if source_poule_id is not None and source_poule_id != candidate.poule_id:
        raise CrawlError(
            f"Requested poule {candidate.poule_id}, but the decoded payload belongs to "
            f"poule {source_poule_id}."
        )
    source_season = _season_name_from_text(
        " ".join(
            str(value)
            for value in (
                _find_value(payloads, "seasonname", "season_name"),
                _find_value(payloads, "seasonyear", "season_year", "year"),
            )
            if value is not None
        )
    )
    candidate_year = _season_year(candidate.season_name)
    if source_season is not None and source_season not in {
        candidate.season_name,
        str(candidate_year),
    }:
        raise CrawlError(
            f"Poule {candidate.poule_id} returned season {source_season!r}, "
            f"not {candidate.season_name!r}."
        )

    competition = _as_text(
        _find_value(payloads, "competitionname", "competition", "groupname")
    )
    class_name = _as_text(
        _find_value(payloads, "classname", "class_name", "class", "poulename", "poolname", "poule_name")
    )
    season_name = source_season
    if season_name is None or season_name == str(candidate_year):
        season_name = candidate.season_name
    poule = {
        "poule_id": candidate.poule_id,
        "season_name": season_name,
        "competition": competition,
        "class": class_name,
        "source": f"{BASE_URL}/poule/{candidate.poule_id}",
    }
    return {
        "poule": poule,
        "teams": teams,
        "matches": matches,
        "standings": standings,
        "rankings": rankings,
        "match_details": [],
        "warnings": validate_poule(matches, standings, rankings),
    }


def season_filename(season_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", season_name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")
    if not slug:
        raise CrawlError(f"Cannot create an output filename for season {season_name!r}.")
    return f"{slug}.json"


def write_season_outputs(
    poules: list[dict[str, Any]],
    output_dir: Path,
    region_name: str = REGION_NAME,
) -> list[Path]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for poule in poules:
        season_name = poule["poule"]["season_name"]
        year = _season_year(season_name)
        if not EARLIEST_SEASON_YEAR <= year <= LATEST_SEASON_YEAR:
            raise CrawlError(
                f"Refusing to write out-of-range season data for {season_name!r}."
            )
        grouped.setdefault(season_name, []).append(poule)

    written: list[Path] = []
    used_names: dict[tuple[int, str], str] = {}
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    for season_name, season_poules in sorted(grouped.items()):
        year = _season_year(season_name)
        filename = season_filename(season_name)
        filename_key = (year, filename)
        previous_season = used_names.get(filename_key)
        if previous_season and previous_season != season_name:
            raise CrawlError(
                f"Season names {previous_season!r} and {season_name!r} map to the same filename."
            )
        used_names[filename_key] = season_name
        document = {
            "schema_version": "1.0",
            "retrieved_at": retrieved_at,
            "source": REGION_URL,
            "region": {"region_id": REGION_ID, "name": region_name},
            "season": {"name": season_name, "year": year},
            "poules": sorted(
                season_poules,
                key=lambda item: item["poule"]["poule_id"],
            ),
        }
        year_dir = output_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        destination = year_dir / filename
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(document, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")
        temporary.replace(destination)
        written.append(destination)
    return written


def _load_robots_parser(allow_unavailable: bool) -> RobotFileParser | None:
    robots_url = f"{BASE_URL}/robots.txt"
    request = Request(robots_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read(1_000_000).decode("utf-8", errors="replace")
    except HTTPError as error:
        if error.code == 404:
            body = ""
        elif allow_unavailable:
            print(
                f"WARNING: robots.txt returned HTTP {error.code}; proceeding by explicit override.",
                file=sys.stderr,
            )
            return None
        else:
            raise CrawlError(
                f"robots.txt returned HTTP {error.code}; use "
                "--proceed-if-robots-unavailable only after checking site rules."
            ) from error
    except (URLError, TimeoutError, OSError) as error:
        if allow_unavailable:
            print(
                "WARNING: robots.txt could not be fetched; proceeding by explicit override.",
                file=sys.stderr,
            )
            return None
        raise CrawlError(
            "robots.txt could not be fetched. No crawl was started. If you have checked "
            "the site's rules and still want to proceed, pass "
            "--proceed-if-robots-unavailable."
        ) from error

    if re.match(r"\s*(?:<!doctype\s+html|<html\b)", body, re.IGNORECASE):
        if allow_unavailable:
            print(
                "WARNING: robots.txt returned HTML instead of crawler rules; "
                "proceeding by explicit override.",
                file=sys.stderr,
            )
            return None
        raise CrawlError(
            "robots.txt returned HTML instead of crawler rules. If you have checked "
            "the site's rules and still want to proceed, pass "
            "--proceed-if-robots-unavailable."
        )

    parser = RobotFileParser(robots_url)
    parser.parse(body.splitlines())
    return parser


def _ensure_allowed(parser: RobotFileParser | None, url: str) -> None:
    if parser is not None and not parser.can_fetch(USER_AGENT, url):
        raise CrawlError(f"robots.txt disallows this URL: {url}")


def _poule_tab_url(poule_id: int, tab: str) -> str:
    suffixes = {"m": "", "s": "/s", "p": "/p"}
    return f"{BASE_URL}/poule/{poule_id}{suffixes[tab]}"


def _season_url(season_id: int) -> str:
    return f"{BASE_URL}/season/{REGION_ID}/{season_id}"


def _group_url(group_id: int) -> str:
    return f"{BASE_URL}/group/{group_id}"


def _read_capture(page: Any) -> list[Any]:
    return page.evaluate(
        f"() => window.{PAYLOADS_GLOBAL} || []"
    )


def _navigate_and_capture(
    page: Any,
    url: str,
    parser: RobotFileParser | None,
    expected_collection: str | None = None,
) -> list[Any]:
    _ensure_allowed(parser, url)
    response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    if response is not None and response.status >= 400:
        raise CrawlError(f"Request to {url} returned HTTP {response.status}.")
    if expected_collection is None:
        condition = """() => {
          const captures = window.__badmintonNowPocPayloads || [];
          const hasPoulePayload = captures.some(payload =>
            /"(?:poules|poulelist|pouleid|poule_id)"\\s*:/i.test(JSON.stringify(payload))
          );
          return hasPoulePayload ||
            document.querySelectorAll('a[href*="poule/"]').length > 0;
        }"""
    else:
        condition = """collection => {
          const captures = window.__badmintonNowPocPayloads || [];
          const pattern = new RegExp('"' + collection + '"\\\\s*:\\\\s*\\\\[', 'i');
          return captures.some(payload => pattern.test(JSON.stringify(payload)));
        }"""
    page.wait_for_function(condition, arg=expected_collection, timeout=30_000)
    page.wait_for_timeout(500)
    return _read_capture(page)


def crawl(
    output_dir: Path,
    allow_unavailable_robots: bool = False,
    skip_robots_check: bool = False,
    start_season: str | None = None,
) -> list[Path]:
    if skip_robots_check:
        print(
            "WARNING: skipping robots.txt check because the URL returned HTML, not rules.",
            file=sys.stderr,
        )
        parser = None
    else:
        parser = _load_robots_parser(allow_unavailable_robots)
    _ensure_allowed(parser, REGION_URL)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise CrawlError(
            "Playwright is not installed. Install requirements.txt and run "
            "`python -m playwright install chromium`."
        ) from error

    written: list[Path] = []
    missing_match_details = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                page.add_init_script(CAPTURE_DECODED_PAYLOADS)
                pacer = ApiRequestPacer()

                def pace_api(route: Any) -> None:
                    parsed_url = urlparse(route.request.url)
                    if (
                        parsed_url.hostname in {"badminton.now", "www.badminton.now"}
                        and parsed_url.path.rstrip("/") == "/api"
                    ):
                        pacer.wait()
                    route.continue_()

                page.route("**/*", pace_api)

                def navigate(url: str, expected_collection: str) -> list[Any]:
                    attempts = 3
                    for attempt in range(attempts):
                        try:
                            return _navigate_and_capture(
                                page,
                                url,
                                parser,
                                expected_collection,
                            )
                        except PlaywrightError as error:
                            if (
                                "ERR_CONNECTION_RESET" not in str(error)
                                or attempt == attempts - 1
                            ):
                                raise
                            delay = 2 ** (attempt + 1)
                            print(
                                f"WARNING: connection reset loading {url}; "
                                f"retrying in {delay}s.",
                                file=sys.stderr,
                            )
                            time.sleep(delay)
                    raise CrawlError(f"Navigation attempts exhausted for {url}.")

                region_payloads = navigate(REGION_URL, "seasons")
                seasons = discover_seasons(region_payloads)
                if start_season is not None:
                    season_names = [season.season_name for season in seasons]
                    try:
                        start_index = season_names.index(start_season)
                    except ValueError as error:
                        raise CrawlError(
                            f"Cannot resume: season {start_season!r} is not in the "
                            "region's requested season list."
                        ) from error
                    seasons = seasons[start_index:]
                region_name = _as_text(
                    _find_value(region_payloads, "regionname", "region_name")
                ) or REGION_NAME
                print(
                    f"Discovered {len(seasons)} seasons in region {REGION_ID}, "
                    f"through {LAST_SEASON_NAME}."
                )

                for season in seasons:
                    season_payloads = navigate(_season_url(season.season_id), "groups")
                    groups = discover_groups(season_payloads, season)
                    if not groups:
                        raise CrawlError(
                            f"Season {season.season_name} did not expose any groups."
                        )

                    season_poules: list[dict[str, Any]] = []
                    seen_poule_ids: set[int] = set()
                    print(
                        f"Collecting {season.season_name}: "
                        f"{len(groups)} groups."
                    )
                    for group in groups:
                        group_payloads = navigate(_group_url(group.group_id), "poules")
                        candidates = discover_poules(group_payloads, season, group)
                        print(f"  {group.name}: {len(candidates)} poules.")
                        for candidate in candidates:
                            if candidate.poule_id in seen_poule_ids:
                                raise CrawlError(
                                    f"Season {season.season_name} lists poule "
                                    f"{candidate.poule_id} in multiple groups."
                                )
                            seen_poule_ids.add(candidate.poule_id)
                            tab_payloads: dict[str, list[Any]] = {}
                            for tab in ("m", "s", "p"):
                                tab_payloads[tab] = navigate(
                                    _poule_tab_url(candidate.poule_id, tab),
                                    {"m": "matches", "s": "standings", "p": "results"}[tab],
                                )
                            season_poules.append(
                                normalize_poule(
                                    candidate,
                                    tab_payloads["m"],
                                    tab_payloads["s"],
                                    tab_payloads["p"],
                                )
                            )

                    if not season_poules:
                        raise CrawlError(
                            f"Season {season.season_name} contained no accessible poules."
                        )
                    written.extend(
                        write_season_outputs(
                            season_poules,
                            output_dir,
                            region_name,
                        )
                    )
                    print(
                        f"Wrote {len(season_poules)} poules for {season.season_name}."
                    )
                    missing_match_details = missing_match_details or any(
                        not poule["match_details"] for poule in season_poules
                    )
            finally:
                browser.close()
    except PlaywrightError as error:
        raise CrawlError(f"Browser collection failed: {error}") from error

    for path in written:
        print(f"Wrote {path}")
    if missing_match_details:
        print(
            "WARNING: Match rubber/set details are not included; see each poule's warnings.",
            file=sys.stderr,
        )
    return written


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect available poule data from Badminton NOW region 19, through "
            "voorjaar 2019, as per-season JSON. No database or raw-response files are created."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="Output root directory (default: ./output next to this script).",
    )
    parser.add_argument(
        "--proceed-if-robots-unavailable",
        action="store_true",
        help="Proceed if robots.txt cannot be fetched; use only after checking site rules.",
    )
    parser.add_argument(
        "--skip-robots-check",
        action="store_true",
        help="Skip fetching robots.txt when it is known to be unavailable or invalid.",
    )
    parser.add_argument(
        "--from-season",
        metavar="NAME",
        help="Resume collection at a listed season, e.g. 'voorjaar 2023'.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        crawl(
            args.output_dir,
            args.proceed_if_robots_unavailable,
            args.skip_robots_check,
            args.from_season,
        )
    except CrawlError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
