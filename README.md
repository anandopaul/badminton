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

## Local web explorer

The `web/` POC provides a local player directory, group-aware history timeline,
ranking trends, and same-poule player comparison. It reads the ignored
`output/player_profile.json` file through a development-only local endpoint; it
does not upload data or contact Badminton NOW.

Use Node.js 22 or newer:

```sh
cd web
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. If the profile file is missing, run
`python3 build_player_profiles.py` from the repository root, then refresh the
web app. The dev server binds to loopback and exposes only the exact profile
file. The production build does not include the local data endpoint or player
JSON.

Check the app with:

```sh
npm test
npm run build
```

The player JSON remains Git-ignored. A future hosted version needs an explicit
decision about whether that player data should be public or access-controlled.

## Local Qwen chat

The Ask tab uses a local Python FastAPI service, which retrieves relevant
player/team facts from the existing JSON and calls Ollama's non-streaming
`/api/chat` endpoint. The browser sends requests to same-origin `/api/chat`;
Vite proxies them to the backend. The backend adds the data-grounding
instructions, limits requests to the latest 12 chat messages, and never puts
model configuration in browser code.

The current season exports contain player ranking totals and team-vs-team
fixture scores, but not individual rubber lineups or results. The chat can
compare team fixtures, but it cannot identify which players a specific player
beat or lost to.

**Optional Windows-native alternative:** if using a Windows-accessible copy of
this repository, Vite and FastAPI can both run on Windows and use Ollama's
loopback directly. For the current Dev Container setup, follow the instructions
below instead:

```powershell
# Terminal 1: repository root
py -3.11 -m venv api\.venv
.\api\.venv\Scripts\python.exe -m pip install -r api\requirements.txt
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen2.5-coder:14b"
$env:BADMINTON_DATA_DIR = "$PWD\output"
.\api\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 3001
```

```powershell
# Terminal 2
cd web
$env:RALLY_ATLAS_CHAT_API_TARGET = "http://127.0.0.1:3001"
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. If the JSON files are missing, build them with
`python3 build_player_profiles.py` from the repository root.

The Dev Container reaches Windows Ollama through a portproxy bound to the WSL
adapter address. Keep Ollama bound to Windows loopback; do not expose it on all
network interfaces. The address below is the last verified value and can
change after restarting WSL or Windows.

From **Windows PowerShell** (read-only checks):

```powershell
docker context show
docker info --format '{{.OperatingSystem}} | {{.OSType}} | {{.KernelVersion}}'
ollama list
Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
Get-NetIPAddress -AddressFamily IPv4 | Format-Table InterfaceAlias,IPAddress
netsh interface portproxy show all
```

In **Ubuntu WSL**, confirm the current gateway:

```sh
ip -4 route show default
```

If the forward is missing or stale, first inspect the existing rule and confirm
the current Windows WSL adapter IP matches the Ubuntu WSL gateway. Then, in
**Administrator PowerShell**, set `$wslIp` and add a rule only if one for that
address does not already exist:

```powershell
$wslIp = Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.InterfaceAlias -match 'WSL' } |
  Select-Object -First 1 -ExpandProperty IPAddress
netsh interface portproxy add v4tov4 `
  listenaddress=$wslIp listenport=11434 `
  connectaddress=127.0.0.1 connectport=11434
```

This binds the forward to the WSL adapter rather than all interfaces. Do not
add a firewall rule unless listener/firewall diagnostics show one is needed;
any required rule must be limited to WSL traffic and port 11434. Roll back this
specific forward with:

```powershell
netsh interface portproxy delete v4tov4 `
  listenaddress=172.17.16.1 listenport=11434
```

After the forward is configured, test from the **Rally Atlas Dev Container**.
Replace the example IP with the current WSL adapter address if it has changed:

```sh
curl --fail --max-time 5 http://172.17.16.1:11434/api/tags
curl --fail --max-time 120 \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Reply with exactly: local Qwen ready."}],"stream":false}' \
  http://172.17.16.1:11434/api/chat
```

Once the connection test succeeds, the runner below starts FastAPI with the
configured Ollama URL and starts Vite with its proxy targeting
`http://127.0.0.1:3001`. If no private host route works, use the Windows-native
alternative above or separately evaluate a private Compose Ollama service,
which needs its own model download/storage and verified GPU support.

The model endpoint and model ID are backend environment variables; never add
credentials to React code or commit local environment files. No credentials
are required for the currently configured Ollama endpoint.

### Run both Dev Container services with one command

The Python runner starts FastAPI and Vite together, checks local data and
dependencies, and verifies that the configured Ollama model is reachable. It
does not start or change anything on Windows.

One-time setup in a Dev Container terminal at the repository root:

```sh
python3 -m venv api/.venv
api/.venv/bin/python -m pip install -r api/requirements.txt
npm ci --prefix web
cp .rally-atlas.local.json.example .rally-atlas.local.json
```

Edit `.rally-atlas.local.json` and set `ollama_base_url` to the current Windows
WSL adapter address, for example `http://172.17.16.1:11434`. The local config is
Git-ignored; update it if the address changes. If `output/player_profile.json`
is missing, build it from the collected season files:

```sh
api/.venv/bin/python build_player_profiles.py
```

Each time you want to use Rally Atlas:

```sh
api/.venv/bin/python run_rally_atlas.py
```

Open `http://127.0.0.1:5173`. Press **Ctrl+C** in that terminal to stop both
Dev Container servers. Ollama and the Windows portproxy stay running. To check
the configuration without starting the web servers:

```sh
api/.venv/bin/python run_rally_atlas.py --check
```

Backend tests:

```sh
api/.venv/bin/python -m unittest discover -s api/tests -v
```

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
