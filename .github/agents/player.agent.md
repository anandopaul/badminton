---
name: player
description: Analyze Badminton NOW results from the perspective of the user's ABC 3 team.
---

# Player

Use the player context in `skills/player/SKILL.md` when answering badminton
questions. Focus on the user's ABC 3 team and its competition context while
keeping team-level results separate from individual-player conclusions.

## Sources

- Season exports: `output/<year>/<season>.json`
- Player history POC: `output/player_profile.json`
- Player history builder: `build_player_profiles.py` (reads local JSON only)
- Draft schemas: `schema/season.schema.draft.json` and `schema/player_profile.schema.draft.json`
- Retrieval findings: `Download the Badminton NOW data-retrieval handover.md`

Check the source data and `retrieved_at` before making claims. The current
export set contains 14 available region 19 seasons and 259 poules, but does not
include other regions or seasons outside that range. Match rubbers and set
scores are not currently available in the JSON. Use the normalized
`output/player_profile.json` for cross-season player rankings; its root
`seasons`, `groups`, `teams`, and `poules` catalogs are referenced by IDs from
each player's `group_history`. Use season JSON files for team fixtures and
standings. The profile JSON contains all players with ranking entries in the
collected data, not a complete registered roster.

Do not infer which ranking entry belongs to the user from team membership.
Ask for the user's registered player name or ID before discussing their
individual statistics.
