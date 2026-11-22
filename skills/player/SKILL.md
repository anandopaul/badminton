---
name: player
description: Persistent player context and guidance for analyzing the user's badminton results.
---

# Player skill

## User context

- The user plays for ABC 3.
- The Badminton NOW exports are for region 19, Bossche Badminton Federatie.
  Poule 5022253 is najaar 2026, Senioren, Klasse 3, and includes ABC 3.

## Data management

- Use JSON as the current source of truth. Read badminton exports from
  `output/<year>/`; each file represents one season. The current set contains
  14 available region 19 seasons from najaar 2026 through voorjaar 2019, with
  259 poules total.
- Verify that the relevant season file exists and inspect its `poules` before
  claiming coverage. Check `retrieved_at` before describing results as current.
- Use `schema/season.schema.draft.json` as the structure for these JSON exports.
- Use `output/player_profile.json` for longitudinal player rankings. It contains
  one profile per unique player ID found in the 14 collected seasons, not only
  the current ABC 3 roster.
- Regenerate the profile with `build_player_profiles.py`; it reads local JSON
  only and does not contact Badminton NOW.
- The profile export is normalized: season, group, team, and poule metadata are
  stored once in top-level catalogs. Player appearances refer to those entities
  by ID; do not expect repeated names or season labels in every appearance.
- A profile includes every ranking snapshot available for that player in the
  collected source files. Players with no ranking entry are not discoverable
  from this dataset.
- Do not create or migrate to SQLite yet. SQLite is a future storage plan; wait
  for the user to request that migration.

## JSON query map

- A season file has root fields `schema_version`, `retrieved_at`, `source`,
  `region`, `season`, and `poules`.
- Each `poules[]` entry has `poule`, `teams`, `matches`, `standings`,
  `rankings`, `match_details`, and `warnings`.
- `teams[]` uses `team_id`; `matches[]` uses `match_id` and `match_number`, with
  participants in `team1` and `team2` and their scores in `score1` and `score2`.
  A `null` score means the fixture has no recorded final score.
- `standings[]` is keyed by `team_id`; `rankings[]` uses `player_id` and
  `team_id`. Prefer IDs over names when joining collections, resolving the IDs
  from the current file rather than hard-coding them across seasons.
- For a focused query, load the relevant season file, select the desired
  `poules[]` entry by `poule.poule_id`, resolve ABC 3 in `teams[]`, then filter
  matches, standings, and rankings by its `team_id`.
- Match-detail records may be absent. Check `match_details[]`; do not query or
  infer rubber/set data that is not present.
- In `player_profile.json`, select a player in `players[]` by `player_id`;
  follow `group_history[].group_id` to the `groups[]` catalog. Each appearance
  references a `poule_id`, which resolves to its season, group, class, source,
  and teams in `poules[]`; use `team_id` to resolve team names in `teams[]`.
  The poule resolves to a season whose `source_file` and `retrieved_at` identify
  its season export.
- Use season exports for team fixtures and standings. Player profiles contain
  ranking snapshots, not individual match or rubber results.
- The 2026 standings points match 2 points per win, 1 per draw, and 0 per loss.
  Recheck this against the relevant season before applying it to other exports.

## Analysis guidance

- Prioritize ABC 3 results, standings, fixtures, and opponents.
- Distinguish team results from individual rankings and player statistics.
- Do not assume which ranking entry is the user. Ask for the registered player
  name or player ID before attributing individual results.
- The current exports cover only the listed seasons in region 19; do not imply
  other regions or unlisted seasons were collected.
- `player_profile.json` includes all ranking-listed players in the collected
  seasons, but is not a registered roster. Do not infer a player's personal
  match participation from a team or ranking appearance.
- Do not infer rubber participants, winners, or set scores; match details have
  not yet been collected.
- Cite match numbers, dates, and the source JSON when explaining results.
