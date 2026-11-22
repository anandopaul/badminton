# Badminton NOW JSON exports

The browser-assisted crawler uses the season list on region 19 and collects its
available seasons from **najaar 2026 through voorjaar 2019**, including each
season's groups and poules. For each poule, it collects matches, standings, and
individual rankings. It writes one normalized JSON file per season under
`output/<year>/`.

The crawler does not create a database or save raw API responses. API calls are
sequential and paced at 1.5 seconds.

Generated exports in `output/` contain player names, IDs, rankings, and match
results, so the data folder and the source handover notes are intentionally
excluded from Git. Keep those files local and do not force-add them to commits.

## Setup

Use Python 3.10 or later:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

The site's `/robots.txt` endpoint currently returns the HTML app page rather
than robots rules. After checking the site's terms, skip that invalid endpoint
with:

```sh
python crawl_badminton_now.py --skip-robots-check
```

## Run

```sh
python crawl_badminton_now.py --skip-robots-check
```

To select another output root:

```sh
python crawl_badminton_now.py --output-dir ./output
```

If a run stops, resume from the first season without a complete JSON file:

```sh
python crawl_badminton_now.py --skip-robots-check --from-season "voorjaar 2023"
```

Season files completed before the selected season are left untouched.

Output names are derived from season names, for example:

```text
output/
  2019/
    voorjaar_2019.json
    najaar_2019.json
  2020/
    voorjaar_2020.json
  2026/
    voorjaar_2026.json
    najaar_2026.json
```

Each file contains `schema_version`, `retrieved_at`, `source`, `region`,
`season`, and a `poules` array. Each poule contains `poule`, `teams`, `matches`,
`standings`, `rankings`, `match_details`, and `warnings`.

The draft JSON Schema is `schema/season.schema.draft.json`. The current crawl
produced 14 season files containing 259 poules, including poule `5022253` in
`najaar 2026`; all files were validated against the draft schema.

## Player profiles

Build profiles from the collected local season files with:

```sh
python3 build_player_profiles.py
```

This writes `output/player_profile.json`; it makes no website requests. It
contains one profile for each unique `player_id` with a ranking entry across the
14 collected seasons, combined across groups such as Jeugd and Senioren.
Currently it contains 1,255 players and 6,932 ranking appearances.

The export is normalized to avoid repeating metadata: season, group, team, and
poule details are stored once in top-level catalogs. A player's
`group_history[].appearances[]` references a poule and team by ID and contains
the ranking snapshot. Resolve the season, group, class, team names, and source
file through those catalogs. The schema is
`schema/player_profile.schema.draft.json`.

The export includes only players present in the available ranking data. It is
not a registered roster and does not include player-level match, rubber, or set
results.

## Player agent

The persistent `player` agent is defined in `.github/agents/player.agent.md`.
Its player-specific context is kept in `skills/player/SKILL.md`.

## Known Phase 1 limitation

The handover does not identify the request used to retrieve detailed match
rubbers and set scores. The crawler does not guess that endpoint or fabricate
those records. It leaves `match_details` empty and adds a
`MATCH_DETAILS_PENDING_PHASE_0` warning for each completed match. Matches,
standings, and rankings are written only after their decoded payloads are
recognized; if a required payload is missing or malformed, the run fails rather
than writing a success-shaped incomplete file.

The decoded payloads are intercepted in the browser's JavaScript context and
held in memory only. They are not written to disk.

## Tests

The normalization and season-discovery tests use Python's standard library:

```sh
python3 -m unittest discover -s tests -v
```
