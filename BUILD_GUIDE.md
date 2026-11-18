# Seoul Commute MCP: Build Guide

A step-by-step record of how this project was built, written so it can be
replicated from scratch on a new machine or reused as a template for another
MCP server.

**How this file is maintained:** every time a step is completed, it is added
here with (1) what we did, (2) the exact commands, (3) why, and (4) any
gotchas. New terms go in the Glossary. Changes are logged in the Changelog at
the bottom. `PROGRESS.md` is the short checklist; this file is the long
explanation.

---

## Glossary

| Term | Meaning |
|---|---|
| **MCP (Model Context Protocol)** | An open standard for connecting AI models to outside tools and data. Like USB-C for AI: build a server once, any MCP-compatible app can use it. |
| **429 RESOURCE_EXHAUSTED** | The error an API returns when you have used up your quota (here, Gemini's free-tier daily limit). Waiting for the reset fixes it; retrying straight away does not. |
| **Cache / TTL** | Keeping a recent answer and reusing it instead of asking the API again. TTL (time to live) is how long an answer may be reused, here 30 seconds. |
| **Streamable HTTP** | The MCP transport for servers on the internet: the client sends each message as an HTTP POST to one URL (here `/mcp`). The local alternative is stdio, where the client starts the server as a program. |
| **Stateless server** | Each request carries everything needed to answer it, so no memory of earlier requests is kept and any server instance can handle any request. |
| **CI (continuous integration)** | Running the tests automatically on a server every time code is pushed, so a broken change shows up straight away. Here it is GitHub Actions. |
| **GitHub Actions / workflow** | GitHub's built-in CI. A workflow is a YAML file in `.github/workflows/` that says when to run (on push) and what to run (install, then pytest). |
| **Badge** | A small image at the top of the README that shows live status, such as "tests passing", linked to the latest run. |
| **MIT License** | A short open-source license: anyone may use and change the code if they keep the copyright notice. Without any license, the code is legally "all rights reserved". |
| **Cloud Run** | Google's service that runs a container and gives it an HTTPS URL; it starts instances when requests arrive and stops them when idle. A Cloud Run *job* runs a container once to the end. |
| **Secret Manager** | Google Cloud's store for keys and passwords; Cloud Run reads them at start-up as environment variables. |
| **Budget alert** | A Google Cloud setting that emails you when spending passes a share of an amount you choose. It warns; it does not cut off spending. |
| **Cleanup policy** | Rules on an Artifact Registry repository that delete old container images automatically (here: keep the newest two). |
| **Cold start** | The delay on the first request after a scaled-to-zero service was idle, while a new instance starts. |
| **Slack (route choice)** | How many minutes slower a route may be and still win because it is simpler. The briefing uses 5 minutes: a route with fewer transfers beats the fastest one unless the fastest saves more than that. |
| **pmset** | The macOS command for power settings. `pmset repeat wakeorpoweron` wakes the Mac at a set time, so launchd jobs run on time instead of on the next wake. |
| **PM2.5 / PM10** | Fine dust particles up to 2.5 and 10 micrometres across, in µg/m³. Korean hourly grades: PM2.5 good 0-15, moderate 16-35, bad 36-75, very bad 76+; PM10 good 0-30, moderate 31-80, bad 81-150, very bad 151+. |
| **단기예보 (short-term forecast)** | KMA's hourly forecast for about the next 3 days on the same 5 km grid, issued 8 times a day (02, 05, 08, 11, 14, 17, 20, 23 h) and online about 10 minutes later. |
| **POP** | Probability of precipitation: KMA's chance of rain for an hour, in percent. The briefing treats 60% or more as "rain likely". |
| **Send window** | The span in which a route's briefing may still go out: from its send time until 3 h 15 min later. A run outside it skips the route, so a Mac that wakes at noon doesn't send a stale morning briefing. |
| **Cloud Run job** | A container that runs once to the end and stops, instead of a service that waits for requests. Billed only while it runs. |
| **Cloud Scheduler** | Google Cloud's cron: calls a URL on a schedule (here, the Cloud Run job's `:run` endpoint at 07:45 and 18:00, Seoul time). |
| **MCP server** | A program that exposes *tools* (functions the AI can call). This project is an MCP server. |
| **MCP client / host** | The AI app that connects to servers and lets the model call their tools: Claude Desktop, Cursor, ChatGPT connectors, etc. |
| **Tool** | One function the model can call, e.g. `air_quality(district)`. The model reads the tool's name, parameters and description to decide when to use it. |
| **Tool description** | The function's docstring. It is effectively a prompt: it tells the model what the tool does and how to call it correctly (e.g. "station name in Korean"). |
| **Transport** | How client and server talk. **stdio** = the client starts the server as a child process and they exchange messages over standard input/output (local use). **Streamable HTTP** = server runs on the web (remote use, Phase 5). |
| **MCP Inspector** | A browser-based debugging UI for MCP servers. Lets you list and call tools by hand without any AI involved. |
| **`MCPServer`** | The server class in MCP Python SDK v2 (was called `FastMCP` in v1). `@mcp.tool()` turns a Python function into a tool. |
| **uv** | A fast Python package and project manager. Creates the virtual environment, installs dependencies, and runs scripts (`uv run ...`). |
| **Virtual environment (`.venv`)** | A project-private folder of Python packages so projects don't interfere with each other. uv manages it automatically. |
| **`pyproject.toml`** | Project config: name, Python version, dependencies. |
| **`uv.lock`** | Exact pinned versions of every dependency, so installs are reproducible. Commit it. |
| **`.env`** | File holding secrets (API keys). Loaded at runtime by `python-dotenv`. Never committed (listed in `.gitignore`). `.env.example` is the safe template. |
| **API key** | A personal token that identifies you to an API provider. |
| **Encoding vs Decoding key (data.go.kr)** | data.go.kr shows two versions of the same key. Use the **Decoding** one; `httpx` URL-encodes it for you. Using the Encoding key double-encodes it and auth fails. |
| **data.go.kr (공공데이터포털)** | Korea's national open-data portal. Hosts KMA and AirKorea APIs. |
| **data.seoul.go.kr (서울 열린데이터광장)** | Seoul city's open-data portal. Hosts realtime subway arrivals. |
| **KMA (기상청)** | Korea Meteorological Administration. We use 초단기실황 (ultra-short-term current observations). |
| **Grid nx/ny** | KMA locates places by 5 km grid cells, not lat/lon. Each district maps to one cell (`sources/districts.py`). |
| **base_date / base_time** | Which hourly KMA observation to fetch. Data for HH:00 appears ~40 min later, so before :45 we ask for the previous hour. |
| **AirKorea (에어코리아)** | Korea Environment Corporation's air-quality network. |
| **PM10 / PM2.5** | Fine dust (≤10 µm) and ultrafine dust (≤2.5 µm), in µg/m³. Korean grades: good / moderate / bad / very bad. |
| **async / await** | Python's way to wait for network calls without blocking. MCP tools can be `async def`. |
| **httpx** | Async-capable HTTP library used to call the APIs. |
| **Agent** | (Phase 3) A program that uses a model plus tools on its own, e.g. a scheduled morning briefing, instead of waiting for a user question. |
| **Server instructions** | Server-wide guidance sent to the client on connect (`MCPServer(instructions=...)`). For rules that span all tools, e.g. coverage limits. |
| **Hallucination (in tool use)** | The model stating something as fact that no tool returned, e.g. a stop count from memory. Evals exist to catch this. |
| **SQLite** | A database stored in one file (`briefing.db`), built into Python (`sqlite3`). No server to run. |
| **Idempotent** | Safe to run twice with the same result. The send log makes `run` idempotent: a second run the same day sends nothing. |
| **launchd** | macOS's built-in job scheduler (the Mac version of cron). Jobs are defined in `.plist` files in `~/Library/LaunchAgents/`. |
| **plist** | Apple's XML config format. Ours says what to run (`ProgramArguments`) and when (`StartCalendarInterval`). |
| **`launchctl`** | Command to load (`bootstrap`), unload (`bootout`) and trigger (`kickstart`) launchd jobs. |
| **Telegram Bot API** | HTTPS API for sending messages as a bot. Create a bot with **@BotFather** to get a token. |
| **Chat ID** | The number that identifies your conversation with the bot. The bot can only message you after you message it first. |
| **Rule-based vs LLM** | Rule-based = fixed if/then logic writes the text (free, predictable). LLM = a model writes it (flexible, costs per call). We start rule-based and keep the two swappable. |
| **MCP client (in code)** | Our own program acting as the host: `mcp.Client(StdioServerParameters(...))` starts `server.py`, lists its tools and calls them. Used by `briefing/llm.py`. |
| **Tool-use loop** | Send the model the prompt plus tool list → it replies with tool calls → we run them and send results back → repeat until it replies with plain text. Capped at `MAX_ROUNDS` so a confused model can't loop forever. |
| **Provider** | The company whose model API you call: Anthropic (Claude) or Google (Gemini). Each has its own SDK and message format; the loop is the same idea. |
| **Free tier (Gemini)** | Google AI Studio keys work without a card on Flash / Flash-Lite models, with low rate limits that Google changes often. Free-tier prompts may be used by Google to improve its products. |
| **Fallback** | If the LLM path fails for any reason, use the rule-based text instead, so the morning message always arrives. |
| **Thought signature** | Opaque data in Gemini's reply that must be sent back unchanged in the next request so the model can continue its reasoning. We append the model's whole turn to the history to keep it. |
| **Guardrail in the tool result** | A short rule appended to a tool's output (e.g. "no journey times available: do not state any"). The model reads it right next to the data, so it works even in clients that ignore server instructions. |
| **Direction sign** | The part of `trainLineNm` after ` - `, e.g. `합정방면` (toward 합정). Together with the line, it identifies one platform direction. |
| **Hop / leg** | In the route API, a *hop* is one station-to-station step (one item in `paths`). We merge hops on the same line into a *leg* (one ride), with transfers between legs. |
| **Eval** | A fixed set of test questions with expected behaviour, used to measure how well the model uses the tools. |
| **Journey line** | The briefing line with minutes, stops and transfers to the saved destination station, taken from the `route` API (Step 9). |
| **Schema migration** | Changing the shape of an existing database, e.g. adding a column. `CREATE TABLE IF NOT EXISTS` never changes a table that already exists, so new columns need an `ALTER TABLE` (`store._migrate`). |
| **Rollback journal** | SQLite's safety file (`briefing.db-journal`). Before changing the database it copies the original pages there; if the write fails, the next open copies them back ("rolls back") and deletes the journal. A journal left behind is called a *hot journal*. |
| **pytest** | Python's standard test runner. Finds `tests/test_*.py`, runs every `test_*` function, and reports failures with the values involved. |
| **Test fixture (data)** | A saved API reply in `tests/fixtures/`, so tests run without network or keys. `*_sample.json` are hand-made in the real shape; `live/*.json` are recorded from the real APIs. |
| **pytest fixture (code)** | A function marked `@pytest.fixture` that prepares something a test needs (a temp database, a fake `get_json`). `autouse=True` applies it to every test. |
| **monkeypatch** | pytest's tool for temporarily replacing a function, attribute or environment variable during one test; it is put back afterwards. |
| **Eval runner** | `evals/run.py`: asks each question in `evals/cases.json` through the same MCP client and tool-use loop as the LLM briefing, then grades the answer automatically and writes a report. |
| **Grounding check** | The eval check that every stop count, minute figure and won amount in an answer also appears in some tool result. A number with no source is treated as invented. |
| **Fault injection** | Making a part fail on purpose to test how the rest behaves. `EVAL_FAIL=air_quality` makes that MCP tool answer `Error: HTTP 503` so evals can check the model admits missing data. |
| **MockTransport** | An httpx feature that answers requests with a function you write instead of going to the network. Used to test `sources/http.py`. |
| **Path traversal** | Smuggling `/` or `../` into a value that is pasted into a URL or file path, so the request lands somewhere it shouldn't. Blocked here by encoding every character of the station name (`quote(..., safe="")`). |
| **Redaction** | Replacing secret values (API keys, the access token) with `[redacted]` before text is shown to a model or written to a log. |
| **.gcloudignore** | Like `.gitignore`, but for what `gcloud ... --source .` uploads to Cloud Build. If it exists, gcloud no longer reads `.gitignore`, so it must list `.env` itself. |

---

## Step 0: Get API keys

**What:** Register on both portals and apply for API access.

1. **data.go.kr**: sign up, then apply (활용신청) for:
   - 기상청_단기예보 조회서비스 (KMA weather)
   - 한국환경공단_에어코리아_대기오염정보 (AirKorea air quality)
   - 한국환경공단_에어코리아_측정소정보 (AirKorea stations, for later)

   Dev accounts are auto-approved. One key covers all three.
   Copy it from 마이페이지 → 활용신청 현황 → 일반 인증키 **(Decoding)**.
2. **data.seoul.go.kr**: sign up via the **외국인회원** (foreign member) path,
   then 인증키 관리 → 일반 인증키. Works for realtime subway.

**Gotchas:**
- The 내국인 (Korean national) sign-up path rejects foreign phone verification.
- Seoul subway key: 1,000 calls/day until the app is registered in the 활용사례 gallery.
- New data.go.kr keys can take up to ~1 hour to activate. Before that you get
  `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`.
- The built-in browser blocks JS `confirm()` pop-ups, so some Korean government
  site submit buttons silently do nothing. Use a normal browser.

---

## Step 1: Project setup and plain data scripts

**What:** Create the project with uv and write one plain Python module per data
source, *before* any MCP code.

**Why:** Debug the APIs on their own first. If something fails later you know
it's MCP, not the API.

```bash
mkdir seoul-commute-mcp && cd seoul-commute-mcp
uv init                                    # creates pyproject.toml
uv add httpx python-dotenv "mcp[cli]>=2"   # runtime dependencies
uv add --dev pytest                        # test dependency
cp .env.example .env                       # then paste real keys
```

**Files:**
- `sources/http.py`: shared `get_json()`. Raises `ApiError` on non-200 responses
  and when data.go.kr returns XML (it does this on auth errors even when you
  ask for JSON).
- `sources/config.py`: `get_key()` reads `.env`, fails loudly if a key is missing.
- `sources/districts.py`: 25 districts, English/Korean names, KMA grid, `resolve()`
  for fuzzy names (`Mapo`, `mapo-gu`, `마포`, `마포구`).
- `sources/kma.py`, `sources/airkorea.py`, `sources/subway.py`: one API each,
  returning clean Python dicts.
- `check_keys.py`: smoke test that calls each API once.

**Verify:**
```bash
uv run python scripts/check_keys.py    # expect 3x OK
```

---

## Step 2: Wrap the sources as an MCP server

**What:** `server.py` creates an `MCPServer` and turns 4 functions into tools:
`current_weather`, `air_quality`, `next_trains`, `list_districts`.

**Key ideas:**
- `@mcp.tool()` above a function = a tool. Type hints become the parameter
  schema; the docstring becomes the description the model reads.
- Tools return **short human-readable strings**, not raw JSON. Easier for the
  model, fewer tokens.
- Errors are **returned as text** (`"Error: ..."`), not raised, so the model can
  read them and recover (e.g. retry with a Korean station name).
- `mcp.run(transport="stdio")` at the bottom: local mode for Claude Desktop.

**Skeleton:**
```python
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("seoul-commute")

@mcp.tool()
async def air_quality(district: str) -> str:
    """Current PM10/PM2.5 in a Seoul district. district: 'Mapo' or '마포구'."""
    ...

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**Gotcha:** MCP SDK v2 renamed `FastMCP` to `MCPServer`
(`from mcp.server.mcpserver import MCPServer`). Old tutorials use the v1 name.

---

## Step 3: Test tools in MCP Inspector

**What:** Call each tool by hand, with no AI involved.

```bash
cd ~/Projects/seoul-commute-mcp
uv sync                      # once, or after dependency changes
uv run mcp dev server.py     # opens Inspector in the browser
```

1. Browser opens at `http://localhost:6274` (if not, copy the URL incl.
   `?MCP_PROXY_AUTH_TOKEN=...` from the terminal).
2. Click **Connect** (transport STDIO, command `uv`, args `run server.py`).
3. **Tools** tab → **List Tools** → expect 4 tools.
4. Pick a tool, fill args, **Run Tool**.
5. After editing code: **Restart** / reconnect. Ctrl+C in terminal to stop.

**Test cases:**
| Tool | Input | Expect |
|---|---|---|
| `air_quality` | `Mapo` | real PM values ✅ tested |
| `current_weather` | `Mapo`, `강남구` | temp, rain, humidity, wind |
| `current_weather` | `Hongdae` | clean `Error: Unknown Seoul district` |
| `next_trains` | `강남`, `서울역` | list of trains (`역` stripped) |
| `next_trains` | `Gangnam` | "No arrival data… Check the Korean station name" |
| `next_trains` | `per_direction` `9` | capped at 3 per direction (was: limit `50` capped at 10, before Step 6c) |
| `list_districts` | none | 25 districts |

**Note:** `uv run server.py` on its own prints nothing and waits. That's
normal: it waits for a client, not for you.

---

## Step 4: Harden error handling

**What:** Make every tool return a readable error instead of crashing.

- `ERRORS = (ApiError, ValueError, KeyError, RuntimeError, httpx.HTTPError)` in
  `server.py`, used by every tool's `except`. Covers bad input, API errors,
  missing keys, timeouts and unexpected response shapes.
- `next_trains` clamps `limit` to 1-10 to protect the 1,000 calls/day quota.
  (Later replaced by `per_direction`, see Step 6c: the quota counts calls, not rows.)
- `sources/subway.py` maps Seoul's `INFO-200` (no data) to an empty list, so the
  model gets a helpful hint rather than an API error.

**Why:** A crashed tool call gives the model nothing to work with. An error
string lets it fix its own mistake.

---

## Step 5: Connect to Claude Desktop  ✅

**What:** Register the server in Claude Desktop's config so it starts the server
automatically (stdio).

1. Find uv's absolute path: `which uv` → on this Mac: `/opt/homebrew/bin/uv`.
   (Claude Desktop doesn't use your shell's PATH, so a bare `uv` fails.)
2. Open the config: Claude Desktop → **Settings → Developer → Edit Config**
   (or in Terminal: `open ~/Library/Application\ Support/Claude`).
   This creates the file if missing and reveals it in Finder. The file is
   `~/Library/Application Support/Claude/claude_desktop_config.json`.
   (`~/Library` is your *user* Library, hidden by default; not `/Library`.)
3. Add the server. The file usually already exists with keys like
   `"coworkUserFilesPath"` and `"preferences"`. Add `"mcpServers"` at the
   **top level** beside them (not inside `"preferences"`), and keep the commas
   valid. Safer: merge it with a script after making a backup:
   ```bash
   cd ~/Library/Application\ Support/Claude
   cp claude_desktop_config.json claude_desktop_config.backup.json
   /opt/homebrew/bin/uv run --no-project python - <<'PY'
   import json
   p = "claude_desktop_config.json"
   c = json.load(open(p))
   c.setdefault("mcpServers", {})["seoul-commute"] = {
       "command": "/opt/homebrew/bin/uv",
       "args": ["--directory", "/Users/jasonbenjamin/Projects/seoul-commute-mcp", "run", "server.py"],
   }
   json.dump(c, open(p, "w"), indent=2)
   PY
   ```
   The block it adds looks like this:
   ```json
   {
     "mcpServers": {
       "seoul-commute": {
         "command": "/opt/homebrew/bin/uv",
         "args": ["--directory", "/Users/jasonbenjamin/Projects/seoul-commute-mcp", "run", "server.py"]
       }
     }
   }
   ```
   `--directory` makes uv run inside the project, so it finds `pyproject.toml`
   and `.env`.
4. Fully quit (**Cmd+Q**) and reopen Claude Desktop.
5. Check the tools/connectors menu in the chat box: `seoul-commute`, 4 tools.
6. Ask "Air quality in Mapo?" and approve the tool call.

**Debug:** `tail -50 ~/Library/Logs/Claude/mcp-server-seoul-commute.log`

**Result (2026-11-11):** `seoul-commute` appears under Connectors. All 4 tools
tested live through Claude Desktop:

| Call | Result |
|---|---|
| `current_weather("Mapo")` | `마포구 at 20261111 2100 KST: 9.2°C, no rain, humidity 79%, wind 0.3 m/s.` |
| `current_weather("Hongdae")` | `Error: Unknown Seoul district: 'Hongdae'...` (clean error) |
| `air_quality("노원구")` | `PM10 44 (moderate), PM2.5 29 (moderate)` |
| `next_trains("강남")` | 5 trains, Line 2 and Shinbundang |
| `next_trains("Gangnam")` | `No arrival data... Check the Korean station name.` |
| `next_trains("서울역", limit=50)` | 10 trains (cap works) |
| `list_districts()` | 25 districts |

**Gotcha:** after editing `server.py`, fully restart Claude Desktop (Cmd+Q)
so it relaunches the server with the new code.

**Follow-up fix:** the train list mixed lines with no label (Line 2 and
Shinbundang both stop at 강남). Added a `LINES` map (`subwayId` → line name,
e.g. `1002` → Line 2) in `sources/subway.py`, so each row now reads
`[Line 2] 성수행 - 역삼방면: 6분 50초 후`. Also strip `역` before printing
the header.

---

## Step 6: Natural-question testing (first eval cases)  ✅

**What:** Ask Claude Desktop normal questions in a new chat and watch which
tools it picks and with what arguments. Every mistake becomes an eval case
(Phase 4).

**Questions to try:**
- "Should I wear a mask in Nowon today?" → expect `air_quality("Nowon")`.
- "When's the next train at Gangnam?" → expect it to translate to `강남` itself.
- "Weather in Hongdae?" → Hongdae is a neighbourhood in Mapo. Does it map it,
  or call with `Hongdae` and recover from the error?
- "Commute check: Mapo to Gangnam, leaving now." → expect several tools.
- "What's the air like in Bundang?" → outside Seoul; expect an honest "not supported".

**Log format:** `evals.md`: question, tools called with arguments, verdict,
what fix would help (tool description change, new alias, new tool).

**Result (2026-11-11):** 3 pass, 2 partial. Full table in `evals.md`.
- The model handled translation (Gangnam → 강남), neighbourhood → district
  (Hongdae → Mapo) and out-of-coverage (Bundang) well on its own.
- **Partial #2:** default `limit=5` hid one Line 2 direction at a transfer
  station. Fixed by raising the default to 10.
- **Partial #4:** for "Mapo to Gangnam" it picked the right direction but stated
  "15 stops" (actually 17) as fact. That came from its own memory: the server
  has no routing data. Fixed by adding server **instructions**.

**New concept: server instructions.** `MCPServer(name, instructions="...")`
sends server-wide guidance to the client when it connects, alongside the tool
descriptions. Use it for rules that apply to every tool: coverage limits, what
the server *can't* do, how to label estimates. Tool docstrings are for
per-tool usage.

**Lesson:** evals catch the model filling gaps with confident guesses. The fix
is often telling it what the tools *don't* cover, not adding more tools.

**Re-test (2026-11-12):** #2 now passes (both Line 2 directions and
Shinbundang). #4 is still partial: with the new instructions the model stated
its start-station assumption and picked the right direction, but still said
"roughly 14 stops, about 30-35 min" (actual: 16 stops from Hapjeong). So the
"label your estimates" instruction was only half followed: the hedge was one
word and the number was still wrong. Telling a model to *label* guesses is
weaker than telling it not to make them, or giving it a tool that knows the
answer.

**Fix (2026-11-12):** the server instructions now forbid the guess instead of
asking for a label:
```
This server has NO route planning, stop counts or travel times. Never state a
number of stops or a journey time, not even "roughly" or "about": you have no
data for them and guesses from memory have been wrong. You may name the line and
the direction to take. For stops and travel time, tell the user to check Naver
Map or KakaoMap.
```
Line and direction are still allowed: the model got those right both times, and
they are what `next_trains` needs (which direction to read). Restart Claude
Desktop (Cmd+Q) so it reloads the instructions, then ask #4 again in a new chat.

**Second re-test (2026-11-12 10:52): still ignored.** The model said "about 17
stops, roughly 35-40 minutes" even with the outright ban. Everything else was
right. The likely reason is that Claude Desktop doesn't show the model the
server `instructions` at all (the MCP spec makes them optional for clients), so
neither version of the rule ever reached it. Tool descriptions and tool results
always reach the model, so the rule now lives in three places:

1. Server `instructions` (for clients that use them).
2. The `next_trains` docstring: "Arrivals at ONE station only. No route, stop
   count or journey time: never state those..."
3. The end of every `next_trains` result: `(Arrivals only. No stop counts or
   journey times available: do not state any; refer the user to Naver Map or
   KakaoMap.)`

**Lesson:** put rules where the model is guaranteed to read them. A note right
next to the data, in the tool result, is the hardest to miss. Server
instructions are a bonus, not something to rely on.

### Step 6c: Every line and direction at transfer stations

**Third re-test of #4 (2026-11-12 10:55):** the journey-time rule finally held
(no stop count or time, pointed to Naver Map / KakaoMap). But the model picked
공덕 as the start, and the feed it got showed only one direction for Line 5 and
Line 6, so it told the user there was no train toward Gangnam. A live
`next_trains("공덕")` call showed 10 rows: Line 5 only toward 마포, Line 6 only
toward 대흥, no 애오개 or 효창공원앞 trains.

**Cause:** the tool asked the Seoul API for at most 10 rows. 공덕 has four lines
(5, 6, Airport Railroad, Gyeongui-Jungang), so 8 directions with about 2 trains
each: more than 10 rows, and the cut fell on whole directions. The old
`limit` was meant to save quota, but the quota is **1,000 calls per day, not
rows**: asking for 40 rows costs the same one call as asking for 10.

**Fix:**
- `sources/subway.py`: `arrivals()` now always asks for `FETCH_ROWS = 40`.
- New `per_direction(trains, k)` keeps the next `k` trains for each (line,
  direction sign) pair, so a busy direction can't push out a quiet one, and
  groups the output by line. Express trains (`(급행)`) share a group with
  locals going the same way.
- `next_trains(station, per_direction=2)` replaces `limit` (1-3, default 2).
  The output length now depends on how many directions the station has, not
  on an arbitrary row cap.
- The briefing's `gather()` also gets the full 40 rows, so the `--toward`
  filter can't come up empty at 홍대입구 just because other lines filled the
  first 10 rows.

**Tested offline** with the 공덕 rows from the live call plus the missing
directions added: all 6 directions kept, max 2 each, grouped by line.

**Still to check on the Mac:** that the API really returns more than 10 rows
when asked for 40. Restart Claude Desktop and ask "next trains at 공덕": expect
Line 5 toward 애오개 and Line 6 toward 효창공원앞 too.

**Lesson:** a cap meant to protect a quota needs to cap the thing the quota
counts. Here a row limit saved nothing and silently hid data.

**Checked live (2026-11-12 10:59):** Line 5 toward 애오개 now appears at 공덕,
so the API does return more than 10 rows. The same #4 answer still had a
route error the tools can't catch: it suggested Line 5 "toward 애오개, then
Yeouido" and a transfer to Line 9, but Yeouido is the other way (마포방면).
Banning numbers stopped the stop counts, but the model still builds whole
routes from memory. Only real route data (a route tool) fully fixes that.

**Guardrail (2026-11-12):** until the route tool exists, `next_trains` (its
docstring and the note at the end of every result) also says: do not suggest
transfers or alternative routes, and describe directions only by their
방면/행 text. When the route tool lands, this part of the rule must be
relaxed again, or the model will refuse to use the route tool's answer.

## Step 8: Route tool (Phase 2 add-on)  ✅

**Goal:** answer "how do I get from A to B" from real data, so the model never
has to build routes from memory.

**Data source:** `서울교통공사_최단경로이동정보` (Seoul Metro shortest path) on
data.go.kr, dataset 15143842. Give it a departure and arrival station; it
returns the fastest, shortest or fewest-transfer route with each segment's
stations, times, distances and transfers. It uses the same `DATA_GO_KR_KEY`,
but it is a separate service, so it needs its own 활용신청.

- Endpoint: `https://apis.data.go.kr/B553766/path2/getShtrmPath2`
  (from the official Swagger spec on the dataset page; an older third-party
  write-up used `path/getShtrmPath` with different parameter names).
- Parameters: `serviceKey`, `dataType=JSON`, `dptreStn` (from), `arvlStn` (to),
  `searchDt` (`yyyy-MM-dd HH:mm:ss`, picks the timetable), `searchType`
  (`duration` default / `distance` / `transfer`), optional `exclTrfstns`
  (stations not to transfer at), `thrghStns` (via stations), `schInclYn`
  (`N` = route only, no timetable), `stationValueType` (`name` or `code`).
- Response `body`: `totalReqHr` (s), `totalDstc` (m), `totalCardCrg` (fare),
  `trsitNmtm` (number of transfers), `trfstnNms[]` (transfer stations with
  from/to line), and `paths[]`, one per station-to-station hop: `dptreStn` /
  `arvlStn` (`stnNm`, `lineNm`), `reqHr`, `stnSctnDstc`, `upbdnbSe`
  (direction), `tmnlStnNm` (train's terminus), `trsitYn`, `trainDptreTm`,
  `trainArvlTm`, `wtngHr`.
- Result codes: `00`/`200` success, `10` unknown station name, `11` bad
  date format, `01`/`02` missing station or date, `99` server error.
- Limits: free, dev account auto-approved, 10,000 calls/day.

Alternative considered: bundling the Seoul Metro station-distance CSV
(OA-12034, Lines 1-8) and running Dijkstra locally. No quota and no network,
but no Line 9, Shinbundang or AREX, and transfer times need a second CSV.
The API is the better first try.

**Steps:**
1. On data.go.kr, search `서울교통공사_최단경로이동정보` and click 활용신청.
   Purpose: 앱개발; describe the project in the text box; tick 동의합니다;
   click 활용 신청하기. Approved instantly (2026-11-12).
2. Once approved (dev keys are usually instant, sometimes up to an hour):
   ```bash
   uv run python scripts/debug_route.py            # 홍대입구 -> 강남
   uv run python scripts/debug_route.py 공덕 강남
   ```
   This saves the raw reply to `logs/route_sample.json` without printing the key.
   **Gotcha:** in Claude's built-in browser the 활용 신청하기 button did
   nothing, because the site asks "are you sure?" with a JS `confirm()` and
   the browser blocks those pop-ups. Workaround used: run
   `window.confirm = () => true` in the page first, then click. In a normal
   browser just press OK.
3. Build `sources/route.py` and a `route(from_station, to_station)` tool
   against that sample, then relax the `next_trains` guardrail.

**First live replies (2026-11-12):**
- `공덕 → 강남`: 2 transfers (삼각지 6→4호선, 사당 4→2호선), 2,010 s, 1,650 won.
- `홍대입구 → 강남`: Line 2 toward 합정, 17 stops, no transfer. The same 17 the
  model kept getting wrong from memory.
- Each item in `paths` is one station-to-station hop. A transfer is a hop
  with `trsitYn = "Y"` between the same station on two lines: `reqHr` is the
  walk, `wtngHr` the wait for the next train. Line 2 station codes are `0` +
  the station number (강남 222 = `0222`, 홍대입구 239 = `0239`).
- `totalReqHr` runs from the first train's departure to the final arrival,
  so it doesn't include waiting on the first platform.

**Gotcha:** the first `debug_route.py` run said "station name doesn't exist"
for 홍대입구. The real cause was zsh: pasted with a trailing `# 홍대입구 → 강남`
comment, zsh passed `#` as an argument (interactive comments are off), so the
departure station was literally `#`. `--code` mode (`0239 0222`) showed the
API's name is plain `홍대입구`.

**What was built:**
- `sources/route.py`:
  - `find(src, dst, prefer)` calls the API (search time = now in KST) and
    turns result codes into readable errors (`10` = unknown station name).
  - `legs(body)` collapses hops into rides (line, from, to, `toward` = the
    first station after boarding, train terminus, stop count, times) and
    transfers (walk and wait).
  - `describe(body)` writes the text the model sees, e.g.
    ```
    홍대입구 -> 강남: 38 min, 17 stops, 0 transfers, card fare 1,650 won. Departs 11:26, arrives 12:04 (timetable).
    - 2호선 from 홍대입구 toward 합정, train to 성수: 17 stops to 강남 (11:26-12:04)
    ```
    `toward 합정` matches the `합정방면` sign in `next_trains`, so the model
    can line up the route with live arrivals.
- `server.py`: new tool `route(from_station, to_station, prefer)` with
  `prefer` = `fastest` / `fewest_transfers` / `shortest`.
- Guardrails rewritten. Server instructions, the `next_trains` docstring and
  its result note now say: stop counts, journey times, transfers and
  direction come **only** from `route`, never from memory. The earlier "don't
  suggest transfers / point to Naver Map" rule was removed, since it would
  stop the model using the new tool.
- `briefing/llm.py` prompt: journey times and stop counts only from `route`.
- `tests/fixtures/route_hongdae_gangnam.json`: the real reply, for Phase 4
  tests (contains no key).

**Tested offline:** `describe()` on the real 홍대입구 → 강남 reply, and on a
hand-made 공덕 → 강남 reply with two transfers (ride, transfer with walk and
wait, ride, transfer, ride).

**To test on the Mac:** restart Claude Desktop (Cmd+Q), check that 5 tools are
listed, then ask eval #4 ("Commute check: Mapo to Gangnam, leaving now.") and
"How do I get from Gongdeok to Gangnam?"


---

## Step 7: Morning briefing (Phase 3)  *(in progress)*

**Decisions:** deliver by **Telegram**, write the text with **rules** (no LLM
yet), run on the **Mac with launchd**.

**Design:**
```
launchd (07:45 Mon-Fri)
  → uv run -m briefing.main run
      → store.due_routes()        SQLite: which routes are due today, not yet sent
      → compose.gather()          calls kma / airkorea / subway in parallel
      → compose.compose()         rules → text   (swap for an LLM later)
      → telegram.send()           Bot API → your phone
      → store.mark_sent()         so it never sends twice in one day
```
The briefing calls `sources/` directly, not through the MCP server. With no
LLM there is no model to pick tools, so MCP would add nothing yet. When the LLM
writer arrives, it should go through the MCP server: that is the point of
having one.

**Files:**
- `briefing/store.py`: SQLite tables `routes` (name, home, work, station,
  direction keyword, days) and `sent_log` (route, day). Validates districts and
  days when saving.
- `briefing/compose.py`: `gather()` fetches everything in parallel with
  `asyncio.gather(..., return_exceptions=True)`, so one failing API doesn't kill
  the message. `compose()` applies the rules:
  - umbrella if rain/snow now at either end
  - clothing by temperature (<0, <5, <12, ≥28 °C), strong wind ≥9 m/s
  - mask if PM10 or PM2.5 is *bad* or worse at either end
  - next 3 trains matching the direction keyword (e.g. `합정`)
  - never says "no umbrella needed" when weather or air data is missing
- `briefing/telegram.py`: `send()` and `chat_ids()`.
- `briefing/main.py`: CLI (`add-route`, `list`, `remove`, `preview`, `run`,
  `chat-id`). `run` skips after 11:00 so a Mac waking at lunch doesn't send a
  stale morning briefing.
- `launchd/com.jasonbenjamin.seoul-briefing.plist`: the schedule.

**Setup:**
1. **Create the bot.** In Telegram, message **@BotFather** → `/newbot` → pick a
   name and a username ending in `bot`. Copy the token into `.env` as
   `TELEGRAM_BOT_TOKEN=...`.
2. **Get your chat id.** Open your new bot, press Start, send "hi". Then:
   ```bash
   uv run -m briefing.main chat-id
   ```
   Put the number in `.env` as `TELEGRAM_CHAT_ID=...`.
3. **Save a route.** The `--toward` keyword is a word from the train's
   direction sign (`trainLineNm`, e.g. `성수행 - 합정방면`):
   ```bash
   uv run -m briefing.main add-route work --home Mapo --work Gangnam --station 홍대입구 --toward 합정
   uv run -m briefing.main list
   ```
4. **Preview with live data** (prints, sends nothing):
   ```bash
   uv run -m briefing.main preview work
   ```
5. **Send one now:** `uv run -m briefing.main run --force`
6. **Schedule it:**
   ```bash
   cp launchd/com.jasonbenjamin.seoul-briefing.plist ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jasonbenjamin.seoul-briefing.plist
   launchctl kickstart -p gui/$(id -u)/com.jasonbenjamin.seoul-briefing   # test now
   tail logs/briefing.log
   ```
   To change the time, edit `Hour`/`Minute` in the plist, then `bootout` and
   `bootstrap` again. To remove: `launchctl bootout gui/$(id -u)/com.jasonbenjamin.seoul-briefing`.

**Tested offline (2026-11-11):** invalid district/day rejected; weekday
scheduling; second run same day sends nothing; calm-day, bad-day (snow, cold,
very bad PM2.5) and all-APIs-down messages. Example calm day:
```
🚇 work: Mapo → Gangnam · Thu 07:30

Weather: Mapo 9.2°C, Gangnam 10.9°C, dry
Air: Mapo PM2.5 30 (moderate), Gangnam PM2.5 35 (moderate)

Next trains, 홍대입구 toward 합정:
• [Line 2] 3분 50초 후
• [Line 2] 전역 도착

🧥 Cool: bring a jacket.
```

**Gotchas:**
- `chat-id` once failed with `httpx.ReadTimeout`: Telegram took longer than
  the original 10 s to answer. `telegram.py` now waits up to 30 s, retries
  once, and reports timeouts, a bad token (401/404) or network errors in one
  line, without ever printing the URL (it contains the bot token).
- launchd only runs while the Mac is on. If it's asleep at 07:30 the job runs
  once on wake (hence the 11:00 cut-off).
- launchd doesn't use your shell's PATH: always absolute paths in the plist.
- Bugs caught in offline testing: snow was shown as "rain now", and a total
  outage still said "No umbrella or mask needed". Both fixed. A briefing must
  never give reassuring advice based on missing data.

### Step 7b: LLM writer  *(built and live-tested 2026-11-12)*

**What changed:** the briefing can now be written by a model that fetches its
own data through our MCP server, instead of by the fixed rules.

```
uv run -m briefing.main preview work --writer llm -v
  → briefing/llm.py write()
      → mcp.Client starts `python server.py` over stdio   (our MCP server)
      → list_tools(): current_weather, air_quality, next_trains, list_districts
      → tool-use loop with Claude or Gemini (max 6 rounds)
           model asks for tools → client.call_tool() → results back to model
      → final text
  (any failure → falls back to compose() rules, logs the reason to stderr)
```

**Why through MCP and not `sources/` directly:** this is the point of having a
server. The same four tools Claude Desktop uses are now used by our own agent,
with the same descriptions and error handling. Fixing a tool fixes it for both.

**Which API key? You do not need to pay yet.** The writer supports two providers:

| | Gemini (Google AI Studio) | Claude (Anthropic) |
|---|---|---|
| Cost | Free tier, no card | Prepaid credits (~$0.001 per briefing on Haiku) |
| Key | aistudio.google.com → Get API key | console.anthropic.com → API keys |
| `.env` | `GEMINI_API_KEY=` | `ANTHROPIC_API_KEY=` |
| Default model | `gemini-3.8-flash` | `claude-haiku-5-5` |

One briefing is about 3-4 model calls, so the free tier's daily limit is plenty
for one route per day. Paste one key in `.env`; the writer picks whichever key
is set (Anthropic first). To force one, set `LLM_PROVIDER=gemini` or
`LLM_PROVIDER=anthropic`. To change the model, set `GEMINI_MODEL=` or
`ANTHROPIC_MODEL=`. ChatGPT/OpenAI is not wired in: its API has no free tier, so
it would cost money like Claude without the benefit.

**Install the new dependencies** (`anthropic`, `google-genai` were added to
`pyproject.toml` and `uv.lock`):
```bash
uv sync
```

**Commands:**
```bash
uv run -m briefing.main preview work --writer llm -v   # print, show tool calls on stderr
uv run -m briefing.main compare work                   # rules vs LLM, one after the other
uv run -m briefing.main run --force --writer llm       # send the LLM version to Telegram
```
`--writer rules` stays the default, so launchd keeps sending the rule-based
message until you add `--writer llm` to the plist's `ProgramArguments`.

**The prompt** (`SYSTEM` in `briefing/llm.py`) carries the same advice rules as
`compose.py` (umbrella, clothing by temperature, wind, mask at *bad*), plus
honesty rules: say "unavailable" when a tool fails, never reassure about
something unchecked, no invented journey times, no forecasts (we only have
current conditions), no numbers the tools didn't return. The route comes from
SQLite in the user message.

**How the loop works (both providers):**
1. Send system prompt, route, and the tool list (MCP `input_schema` passed
   straight through: Anthropic takes it as `input_schema`, Gemini as
   `parameters_json_schema`).
2. If the reply contains tool calls, run each with `client.call_tool()` and send
   the results back. Tool errors are sent as text starting with `Error:` (and
   `is_error=True` for Claude) so the model can report them.
3. Stop when the reply is plain text; give up after 6 rounds.

For Gemini we turn off the SDK's automatic function calling and run the loop
ourselves, so both providers behave the same and every call is logged.

**Tested offline (2026-11-12):** the real `server.py` over stdio (4 tools
listed, all schemas accepted by Gemini, `list_districts` works, offline tool
errors and unknown tools come back as `Error:` text); both provider loops
driven by scripted SDK responses (tool calls → results → final text; Gemini
thought signature kept in history); missing key falls back to rules; a model
that never stops is cut off after 6 rounds. Not yet tested against the real
APIs: needs a key and live data, which the test sandbox cannot reach.

**Gotchas:**
- The MCP SDK starts the server with a minimal environment (PATH, HOME, ...),
  not your shell's variables. So `server_params()` sets `cwd` to the project
  folder and `server.py` loads `.env` itself.
- An exception raised inside `async with Client(...)` comes out wrapped in an
  `ExceptionGroup` (from the client's task group), which makes the fallback log
  unreadable. `write()` catches the error inside the block and re-raises it
  outside.
- **First live run (2026-11-12) failed with `404 NOT_FOUND`:** Google no longer
  offers `gemini-2.5-flash` to new API users, and the 404 message names the
  replacement. Default changed to `gemini-3.8-flash`. If it happens again, read
  the 404 text and set `GEMINI_MODEL=` in `.env`; no code change needed.
- The same run first showed only `MCPError: Connection closed`: the model call
  failed, then shutting the MCP server down raised a second error that hid the
  first. `write()` now always reports the model error first.
- Under Python 3.14, importing `google-genai` prints a few `SyntaxWarning: "\/"
  is an invalid escape sequence` lines. Harmless (a bug in their docstrings);
  they stop once Python has cached the compiled files.
- **API keys were leaking into logs.** `httpx` logs every request URL at INFO,
  and our URLs contain the keys (`serviceKey=...` for data.go.kr, the key in the
  path for Seoul). When `llm.py` started `server.py`, those lines showed up in
  the terminal, and under launchd they would go into `logs/briefing.log`.
  `server.py` now sets the `httpx`/`httpcore` loggers to WARNING. Rule: never log
  full URLs for APIs that take the key as a query parameter.
- **"Hang" at `asking gemini-...` was a 503 "high demand" error.** The
  google-genai SDK silently retries 429/5xx with growing backoff, so it looked
  frozen; pressing Ctrl-C then also killed the MCP server child process, which
  the client reported as `MCPError: Connection closed`. Fixes: SDK retries cut
  to 2 short attempts, and `GEMINI_MODEL` takes a comma-separated list so an
  overloaded model falls through to a backup. Run `debug_gemini.py` to see
  which Flash models your key can use.
- Each model call has a 60 s limit (`MODEL_TIMEOUT`), so a hang turns into a
  clear error and the rules fallback still sends.
- Diagnostics: `uv run python scripts/debug_mcp.py` (MCP connection, no model) and
  `uv run python scripts/debug_gemini.py` (one Gemini call, no MCP).
- Gemini counts "thinking" tokens against `max_output_tokens`, so its limit
  is set higher than Claude's or replies can come back empty.
- Free-tier quotas change without notice. If Gemini starts returning 429
  errors, the fallback still sends the rules version; check `logs/briefing.log`.

### Step 7c: Rules writer states every missing piece  ✅

**What:** In the first live `compare work` run (2026-11-12), two calls failed
(Gangnam weather and Mapo air). The LLM message said so; the rules message
just printed `Weather: Mapo 9.5°C, dry` and left Gangnam out, so it looked
complete. `compose()` in `briefing/compose.py` was rewritten so that:

- Each end of the route shows either its value or `unavailable`:
  `Weather: Mapo 9.5°C, Gangnam unavailable, dry in Mapo` and
  `Air: Mapo unavailable, Gangnam PM2.5 35 (moderate)`.
- "dry" names the district when only one end was checked.
- A footer line lists what is missing:
  `⚠️ No data for Gangnam weather, Mapo air: check it yourself.`
- `✅ No umbrella or mask needed.` appears only when all four checks
  (weather and air, both ends) succeeded and none of them triggered advice.
- Advice uses the worst checked end: umbrella if it is raining or snowing at
  either end, clothing from the colder end, wind from the windier end.
  Before, clothing and wind came from the home end only, and if home weather
  failed, rain at work was ignored.
- Error reasons on the phone are cut to one short line (`_why()`), so a
  data.go.kr XML error no longer puts 300 characters of XML into Telegram.
  `gather()` prints the full error to stderr instead, which launchd writes
  to `logs/briefing.log`.

**Tested offline (2026-11-12)** with fake data: all OK (calm day), today's
failure (work weather and home air missing), home weather missing with rain,
cold and wind at work plus bad air at home, and a total outage. Each output
shows every end and never reassures on missing data.

**Check on the Mac:**
```bash
uv run -m briefing.main compare work
```

**Lesson:** "never reassure on missing data" is not enough. The message must
also never *look* complete when it isn't. Silently leaving a value out is a
quieter version of the same mistake.

### Step 7d: Move out of ~/Desktop and schedule with launchd

**Why move:** macOS privacy protection (TCC) guards `~/Desktop`, `~/Documents`
and `~/Downloads`. Apps you start yourself (Terminal, Claude Desktop) have
been granted access, but a launchd job has not. Under launchd, `uv` can't read
`pyproject.toml` and launchd can't even open the log file, so the job fails
with `Operation not permitted` and nothing is logged. Moving the project to
`~/Projects` (not protected) avoids this without granting Full Disk Access.

**Why 07:45, not 07:30:** KMA publishes each hourly observation about 40
minutes late (see base_time in the Glossary). At 07:30 the briefing would use
06:00 weather; at 07:45 it gets 07:00.

**Commands (Terminal on the Mac):**
```bash
# 1. Quit Claude Desktop (Cmd+Q) so it isn't running server.py, then move
mv ~/Desktop/seoul-commute-mcp ~/Projects/
cd ~/Projects/seoul-commute-mcp
rm -rf .venv && uv sync            # rebuild: venv scripts hold the old path

# 2. Point Claude Desktop at the new path (backup first)
cd ~/Library/Application\ Support/Claude
cp claude_desktop_config.json claude_desktop_config.backup.json
sed -i '' 's#/Desktop/seoul-commute-mcp#/Projects/seoul-commute-mcp#' claude_desktop_config.json
grep seoul-commute-mcp claude_desktop_config.json   # should show /Projects/

# 3. Check it still works by hand
cd ~/Projects/seoul-commute-mcp
uv run -m briefing.main preview work

# 4. Install and test the launchd job
cp launchd/com.jasonbenjamin.seoul-briefing.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jasonbenjamin.seoul-briefing.plist
launchctl kickstart -p gui/$(id -u)/com.jasonbenjamin.seoul-briefing
sleep 15; tail logs/briefing.log
launchctl print gui/$(id -u)/com.jasonbenjamin.seoul-briefing | grep -E "state|last exit"
```

**What the kickstart test should show:** today's briefing was already sent
(10:31), and it is after 11:00 or close to it, so the log should say
`nothing due` or be skipped by the 11:00 cut-off, and `last exit code = 0`.
That proves launchd can run the project. The real test is tomorrow's 07:45
message on the phone.

**If something is wrong:**
- `last exit code = 78` or nothing in the log: launchd couldn't open a path.
  Check the plist paths with `plutil -lint` and `ls`.
- Changed the plist? `launchctl bootout gui/$(id -u)/com.jasonbenjamin.seoul-briefing`,
  copy it again, `bootstrap` again.
- Claude Desktop shows no seoul-commute tools: check
  `~/Library/Logs/Claude/mcp-server-seoul-commute.log` for the old path.
- Pasting the whole block into zsh prints `command not found: #` for each
  comment line: interactive zsh doesn't treat `#` as a comment unless
  `setopt interactivecomments` is on. Harmless; the commands still run.
- Restart Claude Desktop (Cmd+Q, reopen) after the move, so it starts
  `server.py` from the new path.

**Result (2026-11-12 10:44):** moved, `uv sync` rebuilt `.venv` (57 packages),
config now points to `~/Projects`, `preview work` OK, kickstart logged
`nothing due` (today's briefing already sent) with `last exit code = 0`.
First scheduled message due 2026-11-13 07:45.

## Step 9: Journey line in the briefing  ✅

**Goal:** the morning message should also say how long the ride is, with the
same honesty rules as the rest: numbers only from the `route` API (Step 8),
and "unavailable" if the call fails.

**What changed:**
- `briefing/store.py`: new `dest` column (destination station, Korean, no
  `역`). Existing databases get it on the next `connect()` through
  `_migrate()`, which runs `ALTER TABLE routes ADD COLUMN dest ...` only if
  the column is missing. New helpers: `set_dest(con, name, station)` and
  `dest(route)` (works for database rows and the plain dicts used in tests).
- `briefing/main.py`: `add-route ... --to 강남` and a new `set-dest` command
  for an existing route (`set-dest work ''` clears it). `list` shows
  `ride to 강남`.
- `sources/route.py`: `summary(body)` gives one line for the briefing, and
  `first_toward(body)` returns the direction of the first ride.
- `briefing/compose.py`: `gather()` adds a sixth parallel call,
  `route.find(station, dest)`, only when the route has a destination. The
  rules writer prints, after the trains:
  ```
  Journey to 강남: 38 min, 17 stops, no transfers (2호선 toward 합정; timetable 11:26-12:04)
  ```
  If the call fails it prints `Journey to 강남: unavailable (...)` and the
  footer lists `journey` as missing. A failed journey does **not** remove
  `✅ No umbrella or mask needed.`, because that line is only about weather
  and air, which were all checked.
- Direction check: if the API's first ride goes toward a different station
  than the saved `toward` keyword, the footer warns:
  `⚠️ Fastest route boards toward 합정, not 신촌 (saved direction). Check before you go.`
  This catches a wrongly saved direction, which would otherwise filter the
  trains to the wrong platform every morning.
- `briefing/llm.py`: the prompt passes the destination station and tells the
  model to call `route` and write one journey line using only the tool's
  numbers (or no journey line if there is no destination).

**Commands:**
```bash
uv run -m briefing.main set-dest work 강남     # done 2026-11-12
uv run -m briefing.main list                   # work: ... ride to 강남 ...
uv run -m briefing.main preview work           # check the journey line live
uv run -m briefing.main compare work           # both writers
```

**Checked live (2026-11-12 14:32):** `preview work` showed
`Journey to 강남: 38 min, 17 stops, no transfers (2호선 toward 합정; timetable 14:37-15:15)`
under the live trains toward 합정, with no direction warning (the API's
direction matches the saved one) and the usual ✅ line.

**Cost:** one extra data.go.kr call per briefing (route API limit is 10,000
calls a day).

**Note on the time:** `totalReqHr` runs from the first train's departure to
arrival. It does not include waiting on the first platform; the live train
lines just above show that wait.

**Gotcha (Cowork VM only):** the first `set-dest` from Claude's Linux VM
failed with `sqlite3.OperationalError: disk I/O error` and left
`briefing.db-journal` behind. SQLite deletes its journal at the end of each
write, and the VM was not allowed to delete files in the project folder
until deletion was approved. After approval, opening the database rolled the
journal back (integrity check `ok`, nothing lost) and `set-dest` worked. On
the Mac itself this cannot happen. If you ever see a leftover
`briefing.db-journal`, don't delete it by hand: just run any briefing command
on the Mac and SQLite will roll it back.

## Step 10: Unit tests with pytest (Phase 4, part 1)  ✅

**Goal:** catch regressions in parsing and in the honesty rules without
spending API quota or needing keys.

**Setup:** `pytest` was already in the `dev` dependency group. Config added
to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]      # so tests can import sources/, briefing/, server
addopts = "-q"
```

**How the tests stay offline** (`tests/conftest.py`, applied to every test):
- fake `DATA_GO_KR_KEY` and `SEOUL_API_KEY`, so real keys are never used;
- httpx's real network transport is replaced with one that fails the test,
  so an accidental real API call shows up as a failure
  (`test_offline_guard_blocks_real_requests` proves the guard works);
- the `fake_get_json` fixture replaces a source module's `get_json` with a
  function that returns a saved reply and records the URL and parameters,
  so tests can also check what would have been sent.

**Fixtures in `tests/fixtures/`:**
- `route_hongdae_gangnam.json`: real reply (Step 8).
- `route_transfer_sample.json`, `kma_sample.json`, `airkorea_sample.json`,
  `subway_sample.json`: hand-made in the real reply shapes, with fixed values
  so tests can assert exact output.
- `live/*.json`: real replies recorded by `tests/record_fixtures.py` (see
  below). Recorded 2026-11-12: KMA and AirKorea for Mapo, subway at
  홍대입구, route 공덕 to 강남. With them, 69 tests pass and none are skipped.
  The live 공덕 to 강남 route came back via 경의중앙선 to 이촌, then 4호선 to
  사당, then 2호선 (34 min, 2 transfers), not the 6호선/삼각지 route from the
  morning: the fastest route depends on the timetable at search time.

**What is tested (65 tests, 4 more skipped until live fixtures exist):**

| File | Covers |
|---|---|
| `test_districts.py` | 25 districts; spellings (`Mapo`, `mapo-gu`, `마포`, `Jung-gu`); unknown names raise; KMA grid |
| `test_http.py` | JSON OK; XML auth error and HTTP 500 become `ApiError`; offline guard |
| `test_kma_airkorea.py` | KMA base_time (before/after :45, across midnight), parsing, rain, error codes, grid params; AirKorea parsing, missing grade, no rows |
| `test_subway.py` | parsing and line names, `역` stripped and 40 rows requested, INFO-200 means no trains, other codes raise, `per_direction` keeps 2 per sign and groups by line |
| `test_route.py` | legs (17 stops, toward 합정), transfer walk and wait, `describe`, `summary`, `first_toward`, `find` parameters, error codes 10 and 99, empty body |
| `test_store.py` | add and normalise, bad day or district, `set_dest`, weekday scheduling and the send log, migration of an old database |
| `test_compose.py` | calm day, missing ends never reassure, rain and cold from the worse end, mask, total outage, journey line, direction mismatch, failed journey, `gather` adds the journey only with a destination |
| `test_server.py` | MCP tool functions: `list_districts`, `route` text and errors, `next_trains` clamp and guardrail text, missing key returned as text |
| `test_live_fixtures.py` | the parsers on real recorded replies (shape only) |

**Run on the Mac:**
```bash
uv run pytest                                   # all tests, under a second
uv run pytest tests/test_compose.py -v          # one file, each test named
uv run python tests/record_fixtures.py          # save real replies (5 API calls)
uv run pytest -rs                               # -rs also lists skipped tests
```
`record_fixtures.py` calls each source once through its normal code
(KMA and AirKorea for Mapo, subway at 홍대입구, route 공덕 to 강남) and saves
the raw reply to `tests/fixtures/live/`. Replies contain no keys. After that,
the 4 live tests run instead of being skipped. Re-record whenever an API
might have changed its format.

**Gotchas:**
- A test station name like `없는역` turns into `없는` because the code strips
  a trailing `역`. Use names that don't end in `역` for "unknown station" tests.
- Blocking the network by patching `httpx.AsyncClient.send` also blocked
  `MockTransport`. The guard patches `httpx.AsyncHTTPTransport` (the real
  network transport) instead.
- The tests were first run in Claude's Linux VM with a separate environment
  (`UV_PROJECT_ENVIRONMENT=$HOME/venv-linux uv sync --frozen`) so the Mac's
  `.venv` was not touched. On the Mac plain `uv run pytest` is enough.

- Pasting the run commands with trailing `# comment` text into zsh broke
  them again: zsh passed `#` and the comment words as arguments
  (`briefing: error: unrecognized arguments: # check journey line live`,
  `ERROR: file or directory not found: #`). Paste commands without trailing
  comments, or add `setopt interactivecomments` to `~/.zshrc` once.

**Still to do in Phase 4:** the 30-question eval set for the model
(`evals.md` has 6 so far).

## Step 11: 30-question eval set and runner (Phase 4, part 2)  ✅ *(28/30)*

**Goal:** a repeatable score for "does the model use the tools correctly and
honestly", instead of asking questions in Claude Desktop by hand. The score
goes in the README (Phase 5).

**What was built:**
- `evals/cases.json`: 30 questions in 7 categories: weather (5), air (4),
  coverage (2), trains (6), route (7), commute (4), failure (2). They include
  the original Claude Desktop cases (#4 is now case 23), neighbourhood names
  (Hongdae, Jamsil, Itaewon, Yeouido), two Korean questions, two places outside
  Seoul, a district-and-landmark trip (Mapo to COEX), a user asking for a stop
  count "from memory", and two simulated outages.
- `evals/grade.py`: automatic checks per case: tools that must be called (and
  how often), argument patterns (e.g. `next_trains` station must be exactly
  `강남`), phrases the answer must or must not contain, and the grounding
  check. A case passes only if every check passes.
- `evals/run.py`: runs the cases one by one. It uses a deliberately plain
  system prompt ("you are a helpful assistant with live Seoul data"), so the
  tool descriptions and tool results have to carry the rules, as they do in
  Claude Desktop. `--with-instructions` adds the server instructions to
  compare. Results go to `evals/results/<date>_<time>.json` (everything,
  including tool results) and `.md` (score, per-category table, failed
  checks, every answer).
- `briefing/llm.py`: the tool-use loop is now a general
  `ask(system, prompt, ...) -> (answer, tool log)`; the briefing's `write()`
  calls it. `llm.LAST_MODEL` records which model answered (useful with the
  Gemini fallback list).
- `server.py`: `EVAL_FAIL` environment variable for fault injection. Only the
  eval runner sets it, and only for the failure cases.
- `tests/test_eval_grade.py`: tests for the grader itself (number
  extraction, grounding, every check type) and a check that `cases.json` is
  valid. 73 tests in total now.

**Why the grounding check matters:** the model's worst mistakes so far were
confident stop counts and journey times from memory (15, 14, 17 stops for
the same trip). The check pulls every number followed by stops, minutes or
won out of the answer and looks for it in the tool results. "about 15 stops"
with no `route` call fails, even if the number happens to be right.

**Run on the Mac** (paste without trailing comments):
```bash
uv run python -m evals.run
uv run python -m evals.run --only 23,27,28
uv run python -m evals.run --category route -v
uv run python -m evals.run --with-instructions
```
A full run makes about 30-60 model calls and about 100 API calls (well
inside the data.go.kr and Seoul limits). `--delay` (default 4 s) spaces the
cases out for Gemini's free-tier rate limit. A case where the model API fails
is marked `error` and is not counted as a pass or a fail.

**Rerun and partial results:** reports are rewritten after every case, so a
run stopped halfway keeps what it finished. A new run never overwrites an
earlier file (a `-2` suffix is added within the same minute). To repeat only
the cases that ended in `error`, or chosen cases, and get a merged report:
```bash
uv run python -m evals.run --rerun evals/results/2026-11-12_1500.json
uv run python -m evals.run --rerun evals/results/2026-11-12_1500.json --only 10,19,23,25,28,30
```
Cases that are not repeated are re-graded against the current `cases.json`,
so the merged report always uses today's checks.

**First run (2026-11-12 15:00, Gemini, no server instructions): 22/30.**
The Gemini fallback list meant most answers came from `gemini-3.1-flash-lite`
(3.5-flash was busy), so this is a score for the weakest model in the list.
All weather, air and trains cases passed. The 8 that didn't:

| # | What happened | Cause | Fix |
|---|---|---|---|
| 10 | `ConnectError` | Mac's internet dropped | rerun |
| 19 | no final answer after 6 rounds | model looped (or the same network drop) | rerun |
| 22 | Mapo to COEX: picked 마포 and 삼성, named both, correct route | check too strict (wanted the word "assume") | check now asks for `to_station` 삼성 or 봉은사 |
| 29 | "I can only provide ... for districts within Seoul" | check too strict (only 40 characters allowed between "only" and "Seoul") | widened to 80 |
| 23 | commute check answered with `route` only, no trains, weather or air | model | `route` docstring: for a commute check also call next_trains and weather/air at both ends |
| 25 | "what should I wear" Nowon to Gangnam: weather for Nowon only | model | weather and air docstrings: call once for each district on a trip |
| 28 | route tool down, model said "about 16-17 stops" from memory | model, the old hallucination | every `route` error now ends with "No route data: do not give stop counts, journey times or transfers from memory" |
| 30 | user said "from memory is fine", model said 15 stops (real: 17), no tool call | model | `route` docstring: always call it for stops, times, transfers, fares, even if the user says memory is fine |

Re-graded with the fixed checks, the same answers score 24/30. The grader
caught exactly the failure this project is about (cases 28 and 30), which is
the point of the grounding check. The grader also now counts both ends of a
range ("16-17 stops").

**Rerun after the fixes (2026-11-12 15:26, `--rerun`): 28/30.**
Cases 10, 23, 25 and 28 now pass. The commute check (23) called all six
tools (route, weather and air at both ends, trains); with the route tool
down (28) the model said the lookup was unavailable and gave no count.
Still open:
- **#30** ("from memory is fine"): flash-lite made no tool call and said
  19 stops (real: 17). When the model decides not to call any tool, nothing
  on the server side can reach it; only the client's system prompt could.
  Recorded as a known limit; check it again with a stronger model.
- **#19** ended at the 6-round cap twice. Errors now keep the tool calls made
  before the failure (`error.tool_log`), so the next run shows what looped:
  `uv run python -m evals.run --only 19 -v`.

**Next:** run #19 with `-v`; run the full set pinned to one model.
To compare models fairly, pin one model for a run:
`GEMINI_MODEL=gemini-3.5-flash uv run python -m evals.run`.

**Limits of automatic grading:** regex checks can't judge tone, and a
correct answer phrased in an unexpected way can fail a `must` check. Read the
failed cases in the `.md` report before changing code; if the check was
wrong, fix `cases.json`, not the server.

### Step 11b: Case #19 traced: '서울역' keeps its '역'  ✅

**What happened.** `uv run python -m evals.run --only 19 -v` showed the real
cause of the "round cap" failures. The model called
`route('서울역', '강남')` and got back `No route found.`, then kept trying.
`sources/route.py` strips a trailing '역' from every name, because nearly all
stations are registered without it ('강남', '홍대입구'). Seoul Station is the
exception: its official name in the Seoul Metro database is '서울역'. Sending
'서울' does not give an error code; the API answers `00 성공` with an empty
`paths` list, so the tool had nothing to show and the model had nothing to
answer with.

**How it was confirmed (on the Mac; data.go.kr is not reachable from Claude's VM):**

```
uv run python scripts/debug_route.py 서울 강남
uv run python scripts/debug_route.py 서울역 강남
```

The first returned 319 characters and no paths. The second returned the full
route (4호선 to 충무로, 3호선 to 신사, 신분당선 to 강남).

**The fix.** `find()` now calls the API through a small helper `_call()` and
tries up to four name forms: as given without '역', then with '역' added to the
departure, the arrival, and both. It returns the first reply that has paths.
If none do, it raises an `ApiError` saying a station name did not match, so the
model gets the usual "do not answer from memory" rule instead of an empty
`No route found.`. Normal stations still cost one call; only a mismatch costs
up to four (the quota is 10,000 calls a day).

**Live check (16:04):** `route.find('서울역', '강남')` now returns 30 min, 11 stops,
1 transfer at 사당 (4호선 to 2호선).

**Tests:** two new tests in `tests/test_route.py`
(`test_find_retries_with_yeok`, `test_find_no_paths_anywhere`); 77 pass.

**Gotcha in the same run:** gemini-3.5-flash and gemini-3.7-flash both
returned `429 RESOURCE_EXHAUSTED`. That is the free-tier daily quota used up
by today's eval runs, not a code problem; flash-lite then timed out at 60 s.
Rerun #19 when the quota resets:
`uv run python -m evals.run --only 19 -v`.

## Step 12: Cache subway arrivals  ✅

**Why.** Seoul's realtime subway API allows 1,000 calls a day per key. Today
only Jason uses the server, but once it is deployed as a remote MCP (Phase 5)
every visitor's question spends the same quota. The model also tends to call
`next_trains` for the same station more than once in one conversation. A
short cache stops repeat questions from costing extra calls.

**What was done.** `sources/subway.py` keeps an in-memory cache:
a dictionary from station name to (time fetched, parsed rows).
- `arrivals()` returns the cached rows when the same station was fetched less
  than `SUBWAY_CACHE_SECONDS` ago (default 30). Names are normalised first, so
  '홍대입구역' and '홍대입구' share one entry.
- On a cache hit, each train's `seconds` is reduced by the cache entry's age, so
  countdowns stay roughly right. The Korean message text ('3분 후') is not
  rewritten; with a 30-second window it is at most half a minute old.
- Errors (including the daily-limit error) are never cached, so a temporary
  failure doesn't stick. An empty reply (no trains) is cached like any answer.
- Callers get copies, so nothing they change can corrupt the cache.
- `SUBWAY_CACHE_SECONDS=0` in `.env` turns it off (documented in `.env.example`).

The cache lives in the server process, so it starts empty after each restart.
That is fine for one process; a deployment with several instances would each
keep its own cache (a shared store like Redis would only be worth it at much
higher traffic).

**Why 30 seconds.** Arrival messages count down in minutes, so half a minute of
reuse barely changes what the user sees, while it still absorbs the repeat
calls a model makes inside one answer. A longer window would start showing
stale messages; raise it only if quota becomes a real problem.

**Tests:** five new tests in `tests/test_subway.py` (repeat call served from
cache with adjusted seconds, expiry, per-station keys and the off switch,
errors not cached, copies). `tests/conftest.py` now empties the cache before
every test so tests can't leak into each other. A fake clock (`subway._now`)
makes expiry testable without waiting. 82 tests pass.

## Step 13: Remote MCP on Cloud Run (Phase 5)  ✅ *(live 2026-11-12)*

**Goal.** A public HTTPS URL that any MCP client (Claude.ai custom connector,
MCP Inspector, another agent) can use, so the project is more than "runs on
my Mac". Host: Google Cloud Run in Seoul (`asia-northeast3`). It has a free
tier that covers this traffic, it scales to zero when idle, and the Seoul region
matters because Korean government APIs may block or slow down overseas IPs.

### 13a: Code (done 2026-11-12)

- `http_app.py` serves the same `mcp` object from `server.py` over
  **Streamable HTTP**, stateless with JSON replies, so any instance can answer
  any request. `server.py` and stdio use (Claude Desktop, the briefing) are
  unchanged.
- **Access token.** A public URL without protection would let anyone spend the
  data.go.kr and Seoul quotas. `TokenGate` rejects `/mcp` requests unless they
  carry `MCP_ACCESS_TOKEN`, either as `Authorization: Bearer <token>` or as
  `?key=<token>` in the URL (for clients that only take a URL). The comparison
  uses `hmac.compare_digest` so the token can't be guessed from timing.
- `/health` answers `ok` without a token, for uptime checks. (First named
  `/healthz`; Cloud Run reserves paths ending in `z` such as `/healthz` and
  answers them with Google's own 404 page before they reach the container.)
- `Dockerfile` (python:3.14-slim + uv, dependencies installed from `uv.lock`
  before the code is copied, so code changes rebuild fast) and `.dockerignore`
  (keeps `.env`, `briefing.db`, logs and tests out of the image).
- `check_keys.py` now also checks the route API, and doubles as the probe job.
- The LLM SDKs (`anthropic`, `google-genai`) moved to a dependency group `llm`.
  `[tool.uv] default-groups = ["dev", "llm"]` keeps local `uv run` exactly as
  before, while the Dockerfile installs with `--no-default-groups`, so the
  server image carries only what the server imports.
- Tests: `tests/test_http_app.py` (health check, missing/wrong token gives 401,
  `tools/list` works with the token in a header and in the URL). 87 tests pass.

Try it locally before deploying:

```
PORT=8080 MCP_ACCESS_TOKEN=test uv run python http_app.py
```

Then in a second terminal:

```
curl localhost:8080/health
```

### 13b: Google Cloud account and CLI (one time)

1. Go to console.cloud.google.com, sign in with a Google account, and accept
   the free trial (needs a card; new accounts get trial credits, and Cloud Run's
   free tier stays after the trial).
2. Install the CLI on the Mac and log in:

```
brew install --cask google-cloud-sdk
```
```
gcloud init
```

3. Create a project. The ID must be unique across all of Google Cloud. This
   project's ID is `seoul-mcp` (created in `gcloud init`). Set it once per terminal:

```
PROJECT_ID=seoul-mcp
```
```
gcloud projects create $PROJECT_ID
```
```
gcloud billing accounts list
```
```
gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```
```
gcloud config set project $PROJECT_ID
```
```
gcloud config set run/region asia-northeast3
```
```
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

4. Store the keys in **Secret Manager** (not as plain environment variables, so
   they never show in the Cloud Run console or the deploy command):

```
grep '^DATA_GO_KR_KEY=' .env | cut -d= -f2- | tr -d '\n' | gcloud secrets create DATA_GO_KR_KEY --data-file=-
```
```
grep '^SEOUL_API_KEY=' .env | cut -d= -f2- | tr -d '\n' | gcloud secrets create SEOUL_API_KEY --data-file=-
```
```
openssl rand -hex 24 | tr -d '\n' | gcloud secrets create MCP_ACCESS_TOKEN --data-file=-
```

5. Let Cloud Run read them. Cloud Run runs as the project's default compute
   service account:

```
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
```
```
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

6. Budget alert. It emails you at 50% and 100% of US$5. It does **not** stop
   spending; it is an early warning (the real caps are the token and
   `--max-instances 1`). If asked to enable the budgets API, answer yes.
   Gotcha: paste the real billing ID from `gcloud billing accounts list`; a
   leftover placeholder gives `INVALID_ARGUMENT: Invalid billing account name`.

```
gcloud billing budgets create --billing-account=BILLING_ACCOUNT_ID --display-name=seoul-commute --budget-amount=5USD --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
```

**What it costs.** Expected US$0 a month. Seoul is a Tier 2 region, with a
smaller free tier (about 128,000 vCPU-seconds a month), but one tool call uses
1-3 seconds, and idle time is not billed unless minimum instances are set.
Small charges to know about: stored images beyond 0.5 GB (US$0.10 per GB a
month; handled by the cleanup policy in 13d), and Cloud Build minutes beyond
the daily free allowance (only with many deploys a day). Never add
`--min-instances`: that bills an instance around the clock.

### 13c: Probe first: do the Korean APIs answer from Google's servers?

Run `check_keys.py` once as a Cloud Run **job** (a container that runs to the
end instead of serving requests). This builds the image too, so the service
deploy afterwards is quick.

```
gcloud run jobs deploy api-probe --source . --command python --args scripts/check_keys.py --set-secrets DATA_GO_KR_KEY=DATA_GO_KR_KEY:latest,SEOUL_API_KEY=SEOUL_API_KEY:latest --max-retries 0 --execute-now --wait
```
```
gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=api-probe' --limit 30 --format='value(textPayload)'
```

Four `OK` lines mean the APIs accept Google's Seoul IPs. **Result (2026-11-12
16:51): all four OK**, including the route API and live arrivals at 강남. A timeout or 403 on
one of them means that API blocks cloud IPs; stop there and note which one.

### 13d: Deploy the service

```
gcloud run deploy seoul-commute-mcp --source . --allow-unauthenticated --max-instances 1 --memory 512Mi --set-secrets DATA_GO_KR_KEY=DATA_GO_KR_KEY:latest,SEOUL_API_KEY=SEOUL_API_KEY:latest,MCP_ACCESS_TOKEN=MCP_ACCESS_TOKEN:latest
```

Why these flags:
- `--allow-unauthenticated` turns off Google's own sign-in requirement; the
  access token is the lock instead (MCP clients can't sign in to Google).
- `--max-instances 1` caps cost if the URL leaks and keeps a single subway
  cache, so repeat questions don't multiply API calls.

Check it, then get the URL for clients:

```
SERVICE_URL=$(gcloud run services describe seoul-commute-mcp --format='value(status.url)')
```
```
curl $SERVICE_URL/health
```
```
echo "$SERVICE_URL/mcp?key=$(gcloud secrets versions access latest --secret=MCP_ACCESS_TOKEN)"
```

That last line is the connector URL. Treat it like a password.

End-to-end check without printing the token (done 2026-11-12 17:02: the reply
listed `current_weather` and the other tools):

```
TOKEN=$(gcloud secrets versions access latest --secret=MCP_ACCESS_TOKEN)
```
```
curl -s -X POST "$SERVICE_URL/mcp" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 400
```

Last, keep only the two newest images, so old ones don't pile up past the
free 0.5 GB. The repository `cloud-run-source-deploy` is created by the first
`--source` deploy. Without `--no-dry-run` the policy only logs what it would
delete.

```
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy --location=asia-northeast3 --policy=deploy/cleanup-policy.json --no-dry-run
```

**Gotchas to watch for:**
- Cloud Run reserves some paths ending in `z` (`/healthz`, `/readyz`): its
  front end returns a Google-branded 404 and the request never reaches the app.
  Use `/health`.
- `gcloud run jobs deploy` refuses to run if `core/project` holds the project
  *number* (627485706928), which `gcloud init` can set. Fix with
  `gcloud config set project seoul-mcp` (the ID, not the number).
- If the build fails with a permission error, newer projects build with the
  compute service account and it may need `roles/cloudbuild.builds.builder`.
- The first request after an idle period takes a few seconds (cold start).
- Never set `EVAL_FAIL` on the service; it is only for eval fault injection.

---

## Step 14: Security fixes after going live  ✅

**Why.** Once the server had a public URL, a review (2026-11-12) found a few
things worth fixing before sharing it more widely. Anyone holding the token can
call the tools, so tool inputs now count as untrusted.

**What changed.**
- **Station names are encoded completely.** `sources/subway.py` puts the
  station name into the Seoul API's URL path. `quote(station)` used to leave `/`
  as it is, so a name like `../../x` could steer the request (with our key) to a
  different Seoul API endpoint. It is now `quote(station, safe="")`, which turns
  `/` into `%2F`.
- **Length limit on names.** New `check_name()` in `sources/http.py` trims the
  name, drops a trailing '역', and rejects empty names or names over 30
  characters. `next_trains`, `subway.arrivals` and `route.find` all use it.
- **Errors are redacted.** `_err()` in `server.py` now replaces the values of
  `DATA_GO_KR_KEY`, `SEOUL_API_KEY` and `MCP_ACCESS_TOKEN` (plain and
  URL-encoded) with `[redacted]`. Network errors from httpx get a generic message
  because they can contain the request URL, and the URL contains the keys. The
  full, redacted error goes to stderr (Cloud Logging, or `logs/mcp-server.log`
  when the briefing starts the server).
- **`.gcloudignore`.** `gcloud run deploy --source .` used to build its ignore list
  from `.gitignore`, so logs, eval results and the briefing database's journal
  were uploaded to Cloud Build. The new file lists exactly what to leave out.
  It names `.env` itself, because gcloud stops reading `.gitignore` once this file
  exists.
- **The container no longer runs as root.** The Dockerfile adds a system user
  `app` and switches to it with `USER app`.
- **Tests.** `tests/test_security.py`: name limits, `/` encoding, redaction and
  generic network errors. 92 tests pass.

**Redeploy** with the Step 13d command, adding `--concurrency 10` so one
instance can't take a flood of parallel requests:

```
gcloud run deploy seoul-commute-mcp --source ~/Projects/seoul-commute-mcp --allow-unauthenticated --max-instances 1 --concurrency 10 --memory 512Mi --set-secrets DATA_GO_KR_KEY=DATA_GO_KR_KEY:latest,SEOUL_API_KEY=SEOUL_API_KEY:latest,MCP_ACCESS_TOKEN=MCP_ACCESS_TOKEN:latest
```

Then run the `tools/list` curl check from Step 13d and ask the Claude.ai connector
one question.

**Still open (not code).**
- **The token is in the connector URL** (`?key=`). Cloud Run's request logs keep
  full URLs, so the token is stored in Cloud Logging. Rotate it now and then:
  add a new secret version, redeploy, and paste the new URL into the connector.
  ```
  openssl rand -hex 24 | tr -d '\n' | gcloud secrets versions add MCP_ACCESS_TOKEN --data-file=-
  ```
  The long-term fix is OAuth for the connector, which would let `?key=` go.
- **The Seoul subway API is called over plain `http://`**, so that key crosses the
  internet unencrypted. Test whether HTTPS works from the Mac (the Claude VM's
  proxy blocks it):
  ```
  curl -s -o /dev/null -w "%{http_code}\n" "https://swopenapi.seoul.go.kr/api/subway/sample/json/realtimeStationArrival/0/5/%EA%B0%95%EB%82%A8"
  ```
  If this prints `200`, change `BASE` in `sources/subway.py` to `https://`.
- **Budget alert** (Step 13b, item 6) still needs setting up in the console.

**Gotcha: file permissions and the non-root user.** The first deploy with
`USER app` failed with "container failed to start and listen on the port".
`COPY` keeps the files' permissions from the Mac, and files edited by Claude's
VM are owner-only (`-rw-------`), so the `app` user could not read `server.py`.
The Dockerfile now runs `chmod -R a+rX /app` before switching user.

**Gotcha: run from the project folder.** `--source .` means "the folder I'm in".
On 2026-11-12 the deploy was started from `~` by mistake: gcloud tried to pack the
whole home folder (very slow, "Building using Buildpacks" because there was no
Dockerfile) and crashed on a vanished `.claude/ide/*.lock` file. The Step 14
command uses the full path, so it works from any folder.

**Gotcha.** The `echo` line in Step 13d prints the connector URL with the token,
so the token ends up in your terminal scrollback. Clear it, or copy it straight
to the clipboard instead:
`echo "$SERVICE_URL/mcp?key=$(gcloud secrets versions access latest --secret=MCP_ACCESS_TOKEN)" | pbcopy`

### Gotcha: the service's instance went bad (2026-11-17)

In a demo chat every tool except `next_trains` failed with `ConnectTimeout`.
All the failing tools call `apis.data.go.kr`; `next_trains` calls
`swopenapi.seoul.go.kr`. The local server on the Mac worked, and the
`api-probe` job (Step 13c) reached all four APIs from the same region, so
data.go.kr was not blocking Google Cloud. With max 1 instance, every request
went to the same long-running instance, which had stopped connecting.

Fix: start a fresh instance without rebuilding the image:

```
gcloud run services update seoul-commute-mcp --region asia-northeast3 --update-env-vars RESTARTED_AT=$(date +%s)
```

At the time `check_keys.py` always exited 0, so a "successfully completed" probe
proved nothing; read its log (since Step 22 it exits 1 when any API fails):

```
gcloud logging read 'resource.type="cloud_run_job" AND labels."run.googleapis.com/execution_name"="<execution>"' --project seoul-mcp --format='value(textPayload)' --order=asc
```

## Step 15: First real briefing, and a route a commuter would take  ✅

**What happened (2026-11-13).** The first launchd briefing reached Telegram.
`logs/briefing.log` says `2026-11-13 07:50:13 sent work`, five minutes after the
07:45 slot. The likely cause is that the Mac was asleep: launchd does not wake
a sleeping Mac for a `StartCalendarInterval` job; it runs the missed job on the
next wake. To make it punctual, wake the Mac a few minutes earlier:

```
sudo pmset repeat wakeorpoweron MTWRF 07:40:00
pmset -g sched
```

The second command shows the schedule. (Only one `repeat` rule exists at a
time; setting a new one replaces it.)

**The journey line problem.** The same message said:
`Journey to 강남: 36 min, 12 stops, change at 이촌 (경의선 to 4호선), 사당 (4호선 to 2호선)`.
The day before it said 38 min, 17 stops, no transfers on 2호선. The route API's
"fastest" search ranks by timetable time only, so at 08:05 it preferred two
changes to save two minutes. No commuter takes that. It also contradicted the
"Next trains" block (Line 2 toward 합정) and triggered the direction warning.

**Fix.** `sources/route.py` has two new functions:

- `pick_commute(bodies, toward, slack_min=5)` takes several route replies and
  keeps every route within 5 minutes of the fastest. Among those it prefers the
  saved boarding direction, then fewer transfers, then less time.
- `commute(src, dst, toward)` asks the API for both the fastest and the
  fewest-transfers route (two calls in parallel, well inside the 10,000/day
  quota) and picks with `pick_commute`. If one search fails, the other is used;
  if both fail, the error goes to the briefing as before ("unavailable").

`briefing/compose.py` now calls `routes.commute(...)` instead of
`routes.find(...)`, and the direction warning says "Suggested route" instead of
"Fastest route". The `route` MCP tool is unchanged: it still returns what was
asked for (`prefer` = fastest, fewest_transfers or shortest), because a chat
user can ask for either.

**Tests.** `tests/test_route_commute.py` (6 tests): the 2026-11-13 case (2 min
saved, 2 changes: direct route wins), fastest wins when it saves more than the
slack, saved direction beats transfer count, empty replies raise, one failed
search falls back to the other, both failing raises. 98 tests pass.

```
uv run pytest -q
uv run -m briefing.main preview work
```

The second command shows the briefing with the new journey line.

**Gotcha.** The LLM writer (`--writer llm`) still calls the `route` tool, so the
model chooses the search type. If it shows the two-transfer route, add a line to
its prompt asking for `prefer="fewest_transfers"` on commutes.

## Step 16: Air grades from the hourly reading  ✅

**Problem (2026-11-13 preview).** The briefing showed `Mapo PM2.5 25 (n/a)` and
`Gangnam PM2.5 39 (moderate)`, and still said "No umbrella or mask needed". Two
bugs:

1. AirKorea's `pm25Grade` / `pm10Grade` fields follow a 24-hour average and are
   often empty for a few hours after the hourly value appears. So 39 µg/m³,
   which is "bad" on the Korean hourly scale (36-75), came back as "moderate".
2. `compose.py` ranked grades with `GRADE_RANK.get(grade, 0)`, so `n/a` counted
   as "good". That broke the project's main honesty rule: never reassure about
   something that was not checked.

**Fix.**
- `sources/airkorea.py`: new `grade(kind, value, api_grade)` grades the hourly
  number with the Ministry of Environment bands (`BANDS`). It falls back to the
  API's grade only when there is no number (e.g. `-` when a sensor is down),
  and returns `n/a` when there is neither. `current()` uses it for both PM10 and
  PM2.5, so the MCP `air_quality` tool benefits too.
- `briefing/compose.py`: an air reading with an `n/a` grade adds
  "{district} air grade" to the missing list. The footer then says
  "⚠️ No data for Mapo air grade: check it yourself" and the ✅ line is not shown.

**Tests.** Band edges for both pollutants, the 39-but-"moderate" case, fallback
to the API grade, `n/a` with no data, and a compose test that an unknown grade
blocks reassurance.

## Step 17: Rain later in the day (KMA 단기예보)  ✅ *(offline-tested; live check pending)*

**Why.** The briefing only knew current weather. A dry 07:45 with rain at 18:00
meant "No umbrella needed" and a wet trip home.

**API.** `getVilageFcst` in the same KMA service as the current-weather call
(`VilageFcstInfoService_2.0`), so the existing data.go.kr key and 활용신청 cover
it. Issued at 02, 05, 08, 11, 14, 17, 20 and 23 h; we use the latest issue that
is at least 15 minutes old (`kma.forecast_base`). One call with
`numOfRows=1000` returns every category for about 3 days. Categories used:
`TMP` (°C), `POP` (chance of rain, %), `PTY` (0 none, 1 rain, 2 rain/snow,
3 snow, 4 shower; different codes from the observation API) and `PCP`
(1-hour amount as text, e.g. `강수없음`, `1mm 미만`, `2.0mm`).

**Code.**
- `sources/kma.py`: `forecast(district, hours=12)` returns the next 1-24 hourly
  rows from the current hour; `wet_hours(fc)` picks hours with rain or snow
  expected or POP of 60% or more.
- `server.py`: new MCP tool `forecast(district, hours=12)`, with the usual error
  handling and `EVAL_FAIL` support. Server instructions say later weather comes
  only from it.
- `briefing/compose.py`: `gather()` fetches the forecast for both districts
  (2 more data.go.kr calls per briefing), 15 hours ahead (`FORECAST_HOURS`),
  so the 07:45 run covers up to 21:00 and the trip home. 12 hours would stop
  at 18:00. New line "Later: no rain expected
  until 19:00" or "Later: rain likely from 18:00 in Gangnam (70%)", plus the tip
  "☂️ Take an umbrella for later (18:00)." when it is dry now. A failed forecast
  is listed as missing and blocks the ✅ line.
- `briefing/llm.py`: the LLM writer's prompt now calls `forecast` at both ends
  and gives the umbrella-for-later advice; the old "do not forecast" line now
  says later weather comes only from the tool.
- Evals: cases 31-33 (forecast question, trip home needing both districts,
  forecast outage). The set has 33 cases now.

**Tests.** `tests/test_forecast.py` (14 tests) uses a synthetic fixture
(`tests/fixtures/kma_forecast_sample.json`, rain 18:00-20:00) built in the
documented reply shape, because the reply could not be recorded from Claude's
VM. `tests/record_fixtures.py` now also saves `live/kma_forecast.json`, and
`test_live_fixtures.py` checks the parser against it. 124 tests pass, 1 skipped
until the live reply is recorded.

**Checked live on the Mac (2026-11-13 14:03):** `preview work` showed
"Later: no rain expected until 01:00" and, with the Step 16 grades,
"Gangnam PM2.5 39 (bad)" with the mask tip.

**Check on the Mac:**

```
uv run python tests/record_fixtures.py
uv run pytest
uv run -m briefing.main preview work
```

The first command records the live forecast reply; the last shows the briefing
with the new "Later:" line. Then redeploy to Cloud Run (Step 14 command) so the
Claude.ai connector gets the `forecast` tool and the new air grades.

**Gotcha.** The forecast's PTY codes are not the observation codes: 4 means
shower in the forecast, while the observation API uses 5-7 for drizzle and
flurries. Keep the two maps separate (`PTY` and `FCST_PTY`).

## Step 18: Prepare the repository for GitHub  ✅ *(pushed 2026-11-13: github.com/Jay02510/seoul-commute-mcp)*

**Checked (2026-11-13).** A script compared every value in `.env` against every
file in the project (outside `.venv`) and searched for `serviceKey=`, `key=` and
`Bearer` followed by a long token: no hits. `MCP_ACCESS_TOKEN` lives only in
Secret Manager. The data.go.kr and Seoul portal user names were removed from
`PROGRESS.md`. `.gitignore` now also covers `briefing.db-journal`, everything in
`logs/` except `.gitkeep` (`route_sample.json` was not covered before) and
`.claude/`.

**Push from the Mac** (git needs to delete its own lock files, which Claude's
VM can't do in this folder):

```
cd ~/Projects/seoul-commute-mcp
git init -b main
git add .
git status
```

Check that `git status` lists no `.env`, `briefing.db` or `logs/*.log`, then:

```
git commit -m "Seoul Commute MCP: server, briefing, evals, Cloud Run deploy"
gh repo create seoul-commute-mcp --public --source . --push
```

`gh` needs `brew install gh` and `gh auth login` the first time. Without `gh`,
create an empty repo on github.com and follow its "push an existing repository"
lines.

## Step 19: Evening briefing (per-route send time)  ✅ *(offline-tested)*

**What.** Each route now has its own send time (`at`, `HH:MM`, default `07:45`).
`store.due_routes(con, now)` sends a route only inside its send window: from its
time until 3 h 15 min later (`LATE_WINDOW`; 07:45 + 3 h 15 = 11:00, the old fixed
cut-off, which is gone from `main.py`). So one launchd job that fires at 07:45
and 18:00 sends `work` in the morning and `home` in the evening, and the send
log still stops doubles.

**Code.** `at` column with a migration for existing databases, `--at` on
`add-route`, new `set-time` command, `list` shows the time. The plist has five
more `StartCalendarInterval` entries (weekdays 18:00). Tests: send window edges,
evening vs morning, bad times, migration. 128 tests pass.

**Set it up on the Mac:**

```
uv run -m briefing.main add-route home --home Gangnam --work Mapo --station 강남 --toward 교대 --to 홍대입구 --at 18:00
uv run -m briefing.main list
uv run -m briefing.main preview home
```

Check the preview's journey line: 2호선 from 강남 toward 교대, no transfers. If
the warning says the suggested route boards another way, change `--toward` with
a new `add-route` (remove the old one first). Then reload the launchd job:

```
launchctl bootout gui/$(id -u)/com.jasonbenjamin.seoul-briefing
cp launchd/com.jasonbenjamin.seoul-briefing.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jasonbenjamin.seoul-briefing.plist
```

**Fix after the first `preview home` (14:26).** The route was right (2호선
toward 교대, 17 stops, no transfers), but the briefing said "☂️ Take an umbrella
for later (05:00)": the 15-hour forecast window reached into the next morning.
The briefing now uses only today's forecast hours up to 22:00 (`LATER_UNTIL` in
`compose.py`), so the morning run covers the trip home and the evening run
covers the evening. The MCP `forecast` tool is unchanged. 129 tests.

**Gotcha.** `pmset repeat` holds one wake time only, so the 07:40 wake from
Step 15 can't also cover 18:00. If the Mac is asleep at 18:00, the evening
briefing goes out when it wakes (until 21:15). A permanent fix is to run the
briefing in the cloud (Cloud Run job + Cloud Scheduler) instead of on the Mac.

## Step 20: English station names, and an eval runner that stops on quota  ✅

**English names.** `sources/stations.py` maps about 120 English names and
spellings to the Korean names the APIs expect: `Gangnam` → `강남`,
`Hongik Univ. Station` / `Hongdae` → `홍대입구`, `Seoul Station` → `서울`,
`Euljiro 1(il)-ga` → `을지로입구`, `COEX` → `삼성`. Matching ignores case,
punctuation, "station", "line 2" and bracketed parts, and reads `univ.` as
`university`. `check_name()` calls it, so `next_trains` and `route` both accept
English. Korean passes through unchanged. An unknown English name returns a
clear error ("use the Korean name"), so the model retries in Korean instead of
the API failing on a Latin name. The tool docstrings now say English works.

Gotcha: the security test used `../../x` to prove `/` is encoded; `x` is now an
unknown English name and is refused earlier, so the test uses `../../가`.

**Eval runner.** After 3 quota errors (429) in a row the run stops, marks the
remaining cases "not run: daily quota reached" (so `--rerun` picks them up) and
says so. `--only` accepts ranges (`--only 11-21`). The free tier allows only
about 20-25 Gemini calls a day, so the full run is done in daily batches:

```
GEMINI_MODEL=gemini-3.5-flash uv run python -m evals.run --rerun evals/results/2026-11-14_1932.json --only 11-21 --delay 15
```

Then the next day, the newest results file with `--only 22-33`.

## Step 21: Briefing as a Cloud Run job  ✅ *(live 2026-11-17)*

**Why.** launchd needs the Mac awake, and `pmset` can wake it only once a day.
A Cloud Run job started by Cloud Scheduler sends both briefings on time with
the Mac off.

**Design.** The same Docker image as the MCP server (it now also copies
`briefing/` and `deploy/routes.json`) runs as a job with a different command:
`python -m briefing.main run --routes-file deploy/routes.json`. There is no
database in the cloud, so routes come from `deploy/routes.json` and there is no
send log: Cloud Scheduler fires once at 07:45 and once at 18:00, the job never
retries (`--max-retries 0`), and each route's send window decides which one
goes out. `store.kst_now()` gives Seoul time, because the container runs in UTC
(the briefing's "today" and send windows used the machine's local time before).
The LLM writer is not in the image, so the cloud job uses the rules writer.

**1. Telegram secrets** (check that the `.env` values have no quotes first):

```
cd ~/Projects/seoul-commute-mcp
```
```
grep '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2- | tr -d '\n' | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=-
```
```
grep '^TELEGRAM_CHAT_ID=' .env | cut -d= -f2- | tr -d '\n' | gcloud secrets create TELEGRAM_CHAT_ID --data-file=-
```

**2. Deploy the job** (builds the image from source, about 3-5 minutes):

```
gcloud run jobs deploy seoul-briefing --source ~/Projects/seoul-commute-mcp --region asia-northeast3 --command python --args=-m,briefing.main,run,--routes-file,deploy/routes.json --set-secrets DATA_GO_KR_KEY=DATA_GO_KR_KEY:latest,SEOUL_API_KEY=SEOUL_API_KEY:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest --max-retries 0 --task-timeout 120s --memory 512Mi
```

**3. Test it now** (`--force` sends both routes whatever the time):

```
gcloud run jobs execute seoul-briefing --region asia-northeast3 --args=-m,briefing.main,run,--routes-file,deploy/routes.json,--force --wait
```

Two messages should arrive on Telegram.

**4. Schedule it:**

```
gcloud services enable cloudscheduler.googleapis.com
```
```
SA=$(gcloud projects describe seoul-mcp --format='value(projectNumber)')-compute@developer.gserviceaccount.com
```
```
gcloud run jobs add-iam-policy-binding seoul-briefing --region asia-northeast3 --member serviceAccount:$SA --role roles/run.invoker
```
```
gcloud scheduler jobs create http seoul-briefing-morning --location asia-northeast3 --schedule "45 7 * * 1-5" --time-zone Asia/Seoul --uri "https://run.googleapis.com/v2/projects/seoul-mcp/locations/asia-northeast3/jobs/seoul-briefing:run" --http-method POST --oauth-service-account-email $SA
```
```
gcloud scheduler jobs create http seoul-briefing-evening --location asia-northeast3 --schedule "0 18 * * 1-5" --time-zone Asia/Seoul --uri "https://run.googleapis.com/v2/projects/seoul-mcp/locations/asia-northeast3/jobs/seoul-briefing:run" --http-method POST --oauth-service-account-email $SA
```

Check the plumbing without waiting: `gcloud scheduler jobs run seoul-briefing-morning --location asia-northeast3`
starts the job; outside a send window it sends nothing and logs `nothing due`
(Cloud Run > Jobs > seoul-briefing > Logs).

**5. Retire launchd**, or both the Mac and the cloud will send:

```
launchctl bootout gui/$(id -u)/com.jasonbenjamin.seoul-briefing
```

`briefing.db` stays for `preview` and `compare` on the Mac.

**Cost.** Cloud Scheduler: 3 jobs free per billing account (this uses 2).
The job runs for a few seconds twice a weekday, inside Cloud Run's free tier.

**Gotchas.**
- Routes now live in two places: `briefing.db` on the Mac and
  `deploy/routes.json` for the cloud. To change a cloud route, edit the JSON
  and run the Step 2 command again.
- Redeploy the MCP service too (Step 14 command): the English names are in
  `server.py`'s code path.

## Step 22: Make the repository easy to read for a reviewer  ✅

**Why.** A hiring manager gives a repo about 30 seconds: the README's first
screen, whether the tests pass, whether it looks finished. The code was fine;
the front page had a `TBD` score, an old test count, no license and four loose
scripts next to the server.

**What changed (2026-11-18).**
- `scripts/`: `check_keys.py` and the three `debug_*.py` scripts moved there
  with `git mv` (keeps their history). Each adds the repo root to `sys.path`
  so `from sources import ...` still works. Run them as
  `uv run python scripts/check_keys.py`.
- `check_keys.py` now exits 1 if any API fails, so a Cloud Run probe job shows
  as failed instead of "successfully completed" (the trap from 2026-11-17).
- `Dockerfile` copies `scripts/check_keys.py`; the probe job command is now
  `--args scripts/check_keys.py` (Step 13c). `.gcloudignore` and
  `.dockerignore` skip `scripts/debug_*.py`.
- `evals.md` (the first hand-run checks from Step 6) moved to
  `evals/manual-checks.md`.
- `.github/workflows/tests.yml`: on every push, install the dev group only
  (no LLM SDKs, no keys) and run pytest. Checked first in a clean copy with no
  `.env`: 149 passed.
- `LICENSE` (MIT), README badges (tests, Python, license), the real eval score
  and test count, a "Repository layout" table and a License section.

**Do once on the Mac** (sets the About panel, which lives on GitHub, not in the repo):

```
gh repo edit Jay02510/seoul-commute-mcp --description "MCP server: live Seoul transit, weather and air data for AI assistants, with grounding evals" --homepage "https://www.jason-portfolio.com/case/seoul-commute" --add-topic mcp --add-topic model-context-protocol --add-topic llm-evaluation --add-topic cloud-run --add-topic python --add-topic seoul
```

Then pin the repo on your GitHub profile (Customize your pins).

**Gotchas.**
- The first push after this triggers the workflow; the badge shows "no
  status" until that run finishes (about a minute).
- The Cloud Run images built before this step still have `check_keys.py` at
  the root. Redeploy before running the probe with the new path.

## Next steps

- Eval rerun of the 5 open cases (#24, 28, 31-33); then the final score in README, the case study doc and the portfolio.
- Confirm a cloud briefing arrived, then retire launchd (`launchctl bootout`, Step 21).
- `gh repo edit` and pin the repo (Step 22).
- Budget alert in the console.

---

## Changelog

- 2026-11-11: Guide created. Steps 0-4 documented; Step 5 (Claude Desktop) in progress.
- 2026-11-11: Step 5 done; all tools tested live. Added line names to `next_trains`. Step 6 added.
- 2026-11-11: Step 6 done; 5 eval cases in `evals.md`. Default train limit 10, server instructions added.
- 2026-11-11: Step 7 (Phase 3 briefing) built and tested offline; Telegram + launchd setup pending.
- 2026-11-12: Step 7b LLM writer built (`briefing/llm.py`): MCP client + Claude/Gemini tool-use loop, `--writer` flag, `compare` command, rules fallback. Tested offline; needs an API key for a live test.
- 2026-11-12: Gemini default model changed to `gemini-3.8-flash` (2.5 Flash closed to new users); model errors no longer hidden by MCP shutdown errors.
- 2026-11-12: Stopped httpx from logging API keys; 60 s model timeout; live `-v` trace; `debug_mcp.py` and `debug_gemini.py`.
- 2026-11-12: Gemini 503 handling: short SDK retries, model fallback list in `GEMINI_MODEL`; `debug_gemini.py` lists available Flash models.
- 2026-11-12: Telegram client: 30 s timeout with one retry, readable errors (token never printed).
- 2026-11-12: server.py logs stderr to `logs/mcp-server.log` when started by the LLM writer; `compare` runs LLM first. Telegram set up, first rules briefing received.
- 2026-11-12: Step 7c: rules writer marks each missing end as unavailable, lists missing data in a footer, advises from the worst checked end, short error text on the phone. First LLM briefing delivered to Telegram.
- 2026-11-12: `-v` trace shows tool results up to 800 characters (was 100) so train times quoted by the LLM can be checked.
- 2026-11-12: Step 7d: project moves to `~/Projects` (launchd can't read ~/Desktop), briefing time 07:45 for fresh KMA data. Paths in this guide updated.
- 2026-11-12: Step 7d done: project in `~/Projects`, launchd installed and tested (exit 0).
- 2026-11-12: Eval re-test: #2 pass, #4 still partial (stop count guessed as 14, actual 16).
- 2026-11-12: Server instructions forbid stop counts and journey times (eval #4); route tool stays in the backlog.
- 2026-11-12: Eval #4 still guessed journey time; rule copied into the `next_trains` docstring and result text.
- 2026-11-12: Step 6c: `next_trains` fetches 40 rows and shows up to 2 per line and direction (`per_direction`), replacing the 10-row `limit` that hid directions at 공덕.
- 2026-11-12: Step 6c checked live; eval #4 now fails only on transfer advice from memory.
- 2026-11-12: `next_trains` guardrail also forbids transfers and directions beyond the 방면/행 text. Step 8 (route tool) started: API chosen, `debug_route.py` added.
- 2026-11-12: Shortest-path API approved; official spec (`path2/getShtrmPath2`) recorded in Step 8.
- 2026-11-12: Step 8 built: `sources/route.py`, `route` tool, guardrails now point to `route` instead of forbidding route info. Offline-tested; live test pending.
- 2026-11-12: Step 8 live-tested in Claude Desktop: evals #4 and #6 pass with route data from the tool.
- 2026-11-12: Step 9: journey line in the briefing (`dest` column with migration, `set-dest` and `--to`, `route.summary`, direction mismatch warning, LLM prompt). Route `work` now rides to 강남.
- 2026-11-12: Step 10: pytest suite (65 tests, offline guard, sample fixtures, `record_fixtures.py` for live replies).
- 2026-11-12: Live fixtures recorded on the Mac; 69 tests pass, none skipped. zsh trailing-comment gotcha noted again.
- 2026-11-12: Step 9 checked live: journey line correct for route `work` (17 stops, no direction warning).
- 2026-11-12: Step 11: 30-question eval set (`evals/cases.json`), automatic grader with grounding check, runner with reports, `EVAL_FAIL` fault injection, `llm.ask()` refactor. First run pending.
- 2026-11-12: Step 11 first run: 22/30 (flash-lite mostly). Two checks loosened (#22, #29), stop ranges graded, `route` and weather/air docstrings and `route` error text tightened (#23, #25, #28, #30). Runner saves after every case, never overwrites, `--rerun` with re-grading.
- 2026-11-12: Step 11 rerun: 28/30 (#30 memory answer and #19 round cap open). Error results now keep their tool log.
- 2026-11-12: Step 11b: eval #19 traced to '서울역' (official name keeps '역'); `route.find()` retries with '역' added when a reply has no paths, and raises a clear error if no form matches. 77 tests.
- 2026-11-12: Step 12: 30-second in-memory cache for subway arrivals (`SUBWAY_CACHE_SECONDS`), errors never cached. 82 tests.
- 2026-11-12: Step 13a: `http_app.py` (Streamable HTTP, stateless, token gate, /healthz), Dockerfile, .dockerignore, route check in `check_keys.py`. 87 tests. Steps 13b-d written; deploy pending a Google Cloud account.
- 2026-11-12: Step 13: LLM SDKs moved to the `llm` dependency group (image skips them, local use unchanged); budget alert, cost notes and image cleanup policy (`deploy/cleanup-policy.json`) added.
- 2026-11-12: Gotcha: `core/project` must be the project ID (`seoul-mcp`), not the number.
- 2026-11-12: Health check renamed `/healthz` to `/health` (Cloud Run reserves `/healthz`).
- 2026-11-12: Step 13 live: `seoul-commute-mcp` on Cloud Run (Seoul), `tools/list` verified over HTTPS with the token, image cleanup policy applied.
- 2026-11-12: Step 14: security fixes (full URL-encoding of station names, 30-character limit, redacted and generic tool errors, `.gcloudignore`, non-root container, `--concurrency 10`). 92 tests.
- 2026-11-12: Step 14 deploy command uses `--source ~/Projects/seoul-commute-mcp` (a deploy from `~` tried to upload the home folder).
- 2026-11-12: Dockerfile: `chmod -R a+rX /app` before `USER app` (deploy failed: non-root user couldn't read owner-only files).
- 2026-11-12: Step 14 redeployed to Cloud Run (non-root container, --concurrency 10).
- 2026-11-13: Eval #19 rerun passes (gemini-3.5-flash, 11 stops, 1 transfer; `evals/results/2026-11-13_1347.md`).
- 2026-11-13: Step 15: first launchd briefing confirmed (sent 07:50, Mac asleep; `pmset` wake added to the guide). Briefing journey now uses `route.commute()`: fewest transfers unless the fastest route saves more than 5 minutes. 98 tests.
- 2026-11-13: Step 16: air grades from the hourly value (Korean bands), `n/a` grade blocks the ✅ line.
- 2026-11-13: Step 17: KMA 단기예보 `forecast()` + MCP `forecast` tool, "Later:" line and umbrella-for-later tip in the briefing, LLM prompt updated, eval cases 31-33. 124 tests (1 skipped until the live forecast reply is recorded).
- 2026-11-13: README rewritten for the finished project (architecture, tools, briefing, evals, gotchas); GIF and final score still to add.
- 2026-11-13: Steps 16-17 checked live in `preview work`; briefing forecast window raised to 15 hours (covers the trip home).
- 2026-11-13: Redeployed to Cloud Run with the Step 14 command; `tools/list` shows `forecast`, Claude.ai connector works.
- 2026-11-13: Step 18: secret scan clean, portal user names removed, `.gitignore` extended; push commands written.
- 2026-11-13: Step 19: per-route send time (`at`, send window, `set-time`), plist fires at 07:45 and 18:00 on weekdays. 128 tests.
- 2026-11-13: Case study doc drafted (Claude Docs).
- 2026-11-13: Briefing forecast limited to today's hours up to 22:00 (an afternoon preview warned about rain at 05:00 the next day). 129 tests.
- 2026-11-14: Step 20: English station names (`sources/stations.py`, via `check_name`); eval runner stops after 3 quota errors in a row, `--only` takes ranges.
- 2026-11-14: Step 21: briefing as a Cloud Run job (`run --routes-file`, `deploy/routes.json`, `kst_now()`, image copies `briefing/`), Cloud Scheduler commands. 147 tests.
- 2026-11-14: Step 18 marked done: repo was pushed 2026-11-13.
- 2026-11-14: MCP service redeployed (revision 00006); English names checked live through the Claude.ai connector.
- 2026-11-15: Eval batch 2: 20/33 pass so far. Grader compares station arguments after English-to-Korean translation (case #20 had passed 'Sindorim'). 148 tests.
- 2026-11-16: Checked state before the eval rerun: repo in sync with GitHub (Steps 19-21 pushed); Monday 07:45 briefing sent on time (07:45:28).
- 2026-11-16: Eval batch 3: 28/33 pass, 4 errors (quota). #24 failed the grounding check after the model computed a ride time from timetable times; `route` now gives minutes per ride. 149 tests.
- 2026-11-17: Step 21 live: `seoul-briefing` job deployed, `--force` test sent both routes with Seoul time, Cloud Scheduler jobs at 07:45 and 18:00 (Asia/Seoul). Telegram secrets had been created 2026-11-14.

- 2026-11-17: Cloud service timed out on data.go.kr calls; probe job was fine; new revision (00008) fixed it. Gotcha added under Step 14.
- 2026-11-17: README GIF: screen recording cut to `docs/demo.gif` with `ffmpeg -t 33 -i <recording>.mov -filter_complex "crop=1700:1448:577:0,setpts=PTS/1.5,fps=8,scale=900:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" -loop 0 docs/demo.gif` (crop to the chat column, 1.5x speed, 64-colour palette keeps it at 1.1 MB).
- 2026-11-18: Step 22: scripts moved to `scripts/`, `check_keys.py` exits 1 on failure, GitHub Actions test workflow, MIT license, README badges, score, layout table.
