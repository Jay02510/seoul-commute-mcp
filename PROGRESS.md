# Progress log

## Status (2026-11-13, forecast tool and air-grade fix added)
- [x] Phase 0: API keys
  - data.go.kr: KMA 단기예보, AirKorea 대기오염정보, AirKorea 측정소정보, all approved (dev accounts, valid to 2028-11-11). One key covers all three.
  - data.seoul.go.kr (Seoul 통합회원, foreign member): general key issued; works for realtime subway. Limit 1,000 subway calls/day until the app is registered in the 활용사례 gallery.
- [x] Phase 1: plain scripts in `sources/`, `check_keys.py` gives 3x OK
- [~] Phase 2: MCP server (`server.py`, MCP SDK v2 `MCPServer`), 4 tools
  - [x] Tested `air_quality` in MCP Inspector (`uv run mcp dev server.py`): OK, real data
  - [x] `list_districts` + district resolver checked offline (25 districts; Mapo/mapo-gu/마포/Jung-gu all resolve)
  - [x] Hardened tools: catch network/key/shape errors (`ERRORS` tuple), clamp `next_trains` limit to 1-10, map subway INFO-200 to "no arrival data"
  - [x] Connected to Claude Desktop (claude_desktop_config.json, `/opt/homebrew/bin/uv`)
  - [x] All 4 tools tested live through Claude Desktop: real data, clean errors, limit cap works
  - [x] `next_trains` now shows line name (subwayId map) and strips '역' in the header
  - [x] Natural questions in Claude Desktop: 5 cases logged in `evals.md` (3 pass, 2 partial)
  - [x] Fixes: `next_trains` default limit 10; server `instructions` (Seoul-only coverage, no route data, label estimates)
  - [x] Re-tested eval #2 (pass) and #4 (partial: still guesses stop count, said 14, actual 16) on 2026-11-12
  - [x] Fix for #4: server instructions now forbid stop counts and journey times (route tool stays in backlog)
  - [x] Re-tested #4: still stated stops and time, so server instructions are probably not reaching the model in Claude Desktop. Rule added to the `next_trains` docstring and result text
  - [x] Re-tested #4 (10:55): no stop count or time any more. New problem: at 공덕 the 10-row cap hid Line 5 toward 애오개 and Line 6 toward 효창
  - [x] `next_trains`: always fetch 40 rows (quota counts calls, not rows), show up to 2 per line and direction (`per_direction`, 1-3). Briefing fetches 40 too (BUILD_GUIDE Step 6c)
  - [x] Checked live (10:59): Line 5 toward 애오개 now shows at 공덕
  - [x] Eval #4: model invented a wrong-way transfer. Guardrail added to `next_trains` (no transfers, directions only by 방면/행 text)
  - [x] (Guardrail superseded by the route tool, Step 8)
- [~] Route tool (BUILD_GUIDE Step 8)
  - [x] Chose 서울교통공사_최단경로이동정보 (data.go.kr 15143842, `getShtrmPath`); `debug_route.py` saves a raw sample
  - [x] 활용신청 on data.go.kr: approved instantly 2026-11-12 (dev account, 10,000 calls/day). Official endpoint is `path2/getShtrmPath2` (params `dptreStn`, `arvlStn`); `debug_route.py` updated
  - [x] `debug_route.py` live: 공덕→강남 (2 transfers) and 홍대입구→강남 (17 stops) OK. (An apparent "unknown station" was zsh passing `#` as an argument.)
  - [x] `sources/route.py` (find / legs / describe) + `route` tool; offline-tested on the real reply; fixture saved in `tests/fixtures/`
  - [x] Guardrails now say: route facts only from `route`, never from memory (server instructions, `next_trains`, briefing prompt)
  - [x] Live test in Claude Desktop (11:15): 5 tools; eval #4 pass (마포→강남 via 여의도/신논현), #6 pass (공덕→강남 via 삼각지/사당), numbers quoted from the tool
- [~] Phase 3: morning briefing (decided: Telegram, rule-based text for now, launchd on the Mac)
  - [x] `briefing/` package: SQLite routes + send log, parallel data fetch, rule-based compose, Telegram client, CLI
  - [x] Tested offline: route validation, weekday scheduling, no double sends, calm/bad/outage messages
  - [x] launchd plist at `launchd/` (07:45 Mon-Fri, skips after 11:00; was 07:30, moved for fresh KMA data)
  - [x] Telegram bot via @BotFather, token + chat id in `.env` (telegram.py: 30 s timeout + retry after a ReadTimeout)
  - [x] Route `work` saved (Mapo → Gangnam, 홍대입구 toward 합정); rules briefing received on phone 2026-11-12
  - [x] Moved project to `~/Projects` (launchd can't read ~/Desktop), venv rebuilt, Claude Desktop config updated (BUILD_GUIDE Step 7d)
  - [x] launchd job installed; kickstart test 2026-11-12 10:44: `nothing due`, last exit code 0
  - [x] Confirm the first real 07:45 message (2026-11-13): sent 07:50:13, 5 min late, probably because the Mac was asleep
  - [ ] Wake the Mac before the job: `sudo pmset repeat wakeorpoweron MTWRF 07:40:00` (BUILD_GUIDE Step 15)
  - [x] Journey line picked 경의선 + 4호선 + 2호선 (36 min, 2 transfers) over 2호선 direct (38 min). Fixed: briefing uses `route.commute()` (fastest and fewest-transfers searches, fewest transfers wins unless fastest saves more than 5 min, saved direction preferred). 98 tests (BUILD_GUIDE Step 15)
  - [ ] Check Monday's journey line shows 2호선 direct (2026-11-16 07:45:28 message sent on time; check the text on the phone)
  - [~] LLM writer (decided 2026-11-12)
    - [x] `briefing/llm.py`: starts `server.py` as an MCP client over stdio, lists its tools, runs a tool-use loop (max 6 rounds), returns the final text
    - [x] Two providers: Gemini (free tier, `GEMINI_API_KEY`, `gemini-3.8-flash`) for now, Claude (`ANTHROPIC_API_KEY`, `claude-haiku-5-5`) later. Auto-picks whichever key is set; `LLM_PROVIDER` forces one
    - [x] Prompt: route from SQLite + rules from `compose.py` (umbrella/mask/clothing); short Telegram message; never reassure on missing data; no invented journey times or forecasts
    - [x] CLI: `--writer rules|llm` on `preview` and `run` (falls back to rules on any failure), `-v` shows tool calls, `compare <route>` prints both
    - [x] Tested offline: real server over stdio, both loops with scripted responses, fallback, round cap
    - [x] Gemini key in `.env`, `uv sync` done. `gemini-2.5-flash` 404 for new users; `gemini-3.8-flash` 503/timeouts (overloaded)
    - [x] Added: model fallback list (`GEMINI_MODEL=gemini-3.7-flash,gemini-3.5-flash,gemini-3.1-flash-lite` in `.env`), short SDK retries, 60 s timeout, live `-v` trace, server stderr to `logs/mcp-server.log`, `debug_mcp.py`, `debug_gemini.py`
    - [x] Stopped httpx logging API keys (server.py)
    - [x] First successful live LLM briefing 2026-11-12 (`compare work`): gemini-3.5-flash, 5 parallel tool calls, ~10 s when the model isn't overloaded. 3.7-flash 503/timeout, so `.env` order is now 3.5-flash first
    - [x] Fixed: the rules writer silently dropped Gangnam weather and Mapo air when those calls failed. Now each end shows a value or "unavailable", a footer lists what's missing, advice uses the worst checked end, and full errors go to stderr (2026-11-12, tested offline)
    - [x] LLM briefing sent to Telegram with `run --force --writer llm` (2026-11-12 10:31): different layout from rules, so no fallback
    - [x] Per-route send time + send window; plist also fires weekdays 18:00 (BUILD_GUIDE Step 19, 128 tests)
    - [x] `home` route added (강남 toward 교대, to 홍대입구, 18:00); `preview home` correct: 2호선 direct, 17 stops
    - [x] Fix: briefing forecast uses only today's hours up to 22:00 (preview warned about rain at 05:00 next day). 129 tests
    - [ ] Reload launchd so the 18:00 run is active (or skip: Step 21 replaces launchd)
    - [x] Cloud briefing code: `run --routes-file deploy/routes.json`, Seoul time in the container, image includes `briefing/` (BUILD_GUIDE Step 21)
    - [x] Cloud Run job `seoul-briefing` deployed and tested with `--force` (2026-11-17 17:33: Seoul time in the header, route line OK, rain tip)
    - [x] Cloud Scheduler: `seoul-briefing-morning` (45 7 * * 1-5) and `seoul-briefing-evening` (0 18 * * 1-5), Asia/Seoul, no retries
    - [ ] `launchctl bootout` the Mac job so it doesn't send a second copy
    - [ ] Confirm the first scheduled sends: 2026-11-17 18:00 (home), 2026-11-18 07:45 (work)
    - [ ] Compare rules vs LLM output for a few days; add cases to `evals.md`
    - [ ] Switch launchd to `--writer llm` once it's reliably better
    - [x] Journey line (BUILD_GUIDE Step 9): `dest` column + migration, `set-dest` / `add-route --to`, `route()` in `gather`, warning if the API's direction differs from the saved one; LLM prompt asks for it too. Route `work` set to ride to 강남 (2026-11-12)
    - [x] Journey line checked live (2026-11-12 14:32): `Journey to 강남: 38 min, 17 stops, no transfers (2호선 toward 합정; timetable 14:37-15:15)`, no direction warning
    - [x] Air grades from the hourly value (Korean bands); an `n/a` grade no longer counts as good and blocks "No umbrella or mask needed" (BUILD_GUIDE Step 16, 2026-11-13)
    - [x] KMA 단기예보: `kma.forecast()`, MCP `forecast` tool, briefing "Later:" line and umbrella-for-later tip, LLM prompt, eval cases 31-33 (BUILD_GUIDE Step 17, 2026-11-13, offline-tested with a synthetic fixture)
    - [x] `preview work` live (14:03): "Later:" line, Gangnam PM2.5 39 (bad) with mask tip. Forecast window raised to 15 h so 07:45 covers up to 21:00
    - [x] Live forecast reply recorded; `test_live_kma_forecast` passes (125 tests, none skipped)
    - [x] Redeployed to Cloud Run (2026-11-13 14:14): `forecast` tool live, connector works
- [~] Phase 4: pytest with recorded fixtures, 30-question eval set
  - [x] pytest suite, 65 tests, all offline (BUILD_GUIDE Step 10): districts, http, KMA, AirKorea, subway, route, store, compose, MCP tools
  - [x] Live fixtures recorded on the Mac (2026-11-12 15:04): kma, airkorea, subway, route. 69 tests pass, 0 skipped
  - [x] 30-question eval set built (BUILD_GUIDE Step 11): `evals/cases.json`, `evals/grade.py` (incl. grounding check), `evals/run.py` (reports in `evals/results/`), `EVAL_FAIL` outages, grader tests (73 tests total)
  - [x] First full eval run (2026-11-12 15:00): 22/30, mostly gemini-3.1-flash-lite; 24/30 after fixing two over-strict checks. Real failures: #23, #25 (skipped tools on commute questions), #28, #30 (stop counts from memory)
  - [x] Fixes: `route` docstring (always call it; commute = trains + weather/air at both ends), weather/air docstrings (both districts), `route` errors carry a no-memory rule; runner saves after every case and has `--rerun`
  - [x] Rerun (2026-11-12 15:26): **28/30**. #10, #23, #25, #28 pass now. Open: #30 (no tool call when user says "from memory", said 19 stops, real 17) and #19 (6-round cap)
  - [x] #19 traced (2026-11-12 15:53): `route('서울역','강남')` returned no paths because `find()` stripped '역'. Fixed: retry with '역' added, clear error if no name form matches (BUILD_GUIDE Step 11b, 77 tests)
  - [x] Checked live on the Mac (16:04): 서울역 -> 강남, 30 min, 11 stops, 1 transfer at 사당
  - [x] Rerun #19 (2026-11-13 13:47, gemini-3.5-flash): pass, 11 stops, 1 transfer at 사당 (`evals/results/2026-11-13_1347.md`)
  - [~] Full run pinned to gemini-3.5-flash, in daily batches (free tier allows about 20-25 calls a day)
    - [x] 2026-11-13 14:30: 0/33, all errors (503, then 429 quota)
    - [x] 2026-11-14 19:32: 10/10 graded pass (cases 1-10: weather 5/5, air 4/4, coverage 1/1); 11-33 hit 429 (`evals/results/2026-11-14_1932.json`)
    - [x] 2026-11-15 18:05: 20/33 pass, 1 fail, 12 errors (429 from #22). trains 6/6, route 4/7 so far (`evals/results/2026-11-15_1805.json`)
    - [x] #20 failed only on the args check: the model passed 'Sindorim'/'Yeouido', which the server now translates. Grader now compares station args as the server sees them (148 tests); the next `--rerun` regrades #20
    - [x] 2026-11-16 19:01: **28/33 pass**, 1 fail, 4 errors (`evals/results/2026-11-16_1901.json`). weather 5/5, air 4/4, coverage 2/2, trains 6/6, route 7/7, commute 3/4
    - [x] #24 fail: the model subtracted timetable times to state a 24-minute ride; the grounding check flagged it (right arithmetic, but not a tool number). Fix: `route` now states minutes per ride (`_ride_min`), 149 tests
    - [x] Tue 17:05: rerun of 24,28,31-33 all errored with 503 (Gemini overloaded, not quota); still 28/33 (`evals/results/2026-11-17_1705.json`)
    - [ ] Retry later: `GEMINI_MODEL=gemini-3.5-flash uv run python -m evals.run --rerun evals/results/2026-11-17_1705.json --delay 30`
    - [x] MCP service redeployed for per-ride minutes (2026-11-16 evening)
- [x] Subway arrivals cache, 30 s per station, `SUBWAY_CACHE_SECONDS` (BUILD_GUIDE Step 12, 82 tests)
- [~] Phase 5: remote MCP (Streamable HTTP) deploy, README with GIF + eval scores
  - [x] Host decided: Cloud Run, asia-northeast3 (Seoul)
  - [x] `http_app.py`: Streamable HTTP, stateless JSON, access token (Bearer or ?key=), /healthz; Dockerfile + .dockerignore; 87 tests (BUILD_GUIDE Step 13a)
  - [x] LLM SDKs in `llm` dependency group (server image skips them); cleanup policy file; cost notes (Step 13)
  - [x] Google Cloud account created (2026-11-12)
  - [x] gcloud installed; project `seoul-mcp` created, billing linked, region asia-northeast3, services enabled (2026-11-12)
  - [x] Secrets created; compute service account given `roles/secretmanager.secretAccessor` (2026-11-12)
  - [ ] Budget alert: CLI command failed twice, set it up later in the console (Billing > Budgets & alerts)
  - [x] API probe job from Seoul region (Step 13c, 16:51): all 4 OK (KMA, AirKorea, subway arrivals, route). Korean APIs accept Google Cloud Seoul IPs
  - [x] Service `seoul-commute-mcp` deployed to Cloud Run (asia-northeast3), max 1 instance, secrets from Secret Manager (2026-11-12)
  - [x] Live check 17:02: `tools/list` over HTTPS with the Bearer token returns the tools; image cleanup policy (keep 2) applied
  - [x] Connected in Claude.ai as custom connector "Seoul MCP Cloud" (17:08). 홍대입구 -> 강남 question: weather both ends, Line 2 toward 합정, next trains, 17 stops / 38 min / 1,650 won, all from tools. One ungrounded extra: "don't take the 신촌 direction, it goes the long way round" (true, but from memory; route only returns the chosen direction)
  - [x] Security fixes (BUILD_GUIDE Step 14, 2026-11-12): station names fully URL-encoded (`safe=""`), 30-character limit, tool errors redacted and generic for network errors, `.gcloudignore`, non-root container. 92 tests
  - [x] Redeployed with the Step 14 command (2026-11-12 17:31; first try from ~ crashed, second failed until the Dockerfile made /app readable for the non-root user)
  - [x] Recheck (17:32): Claude.ai connector, next_trains at 홍대입구 returns live data after the redeploy
  - [x] 2026-11-17 21:00: cloud service timed out (ConnectTimeout) on every data.go.kr call; subway still worked. The `api-probe` job reached all 4 APIs, so it was the service's single instance, not a block. Fixed by forcing a new revision (`--update-env-vars RESTARTED_AT=...`, revision 00008); all tools checked live 21:20 (BUILD_GUIDE Step 14 gotcha)
  - [x] README GIF re-recorded 2026-11-17 21:22 (Claude Desktop, incognito, cloud connector only): `docs/demo.gif`, 900 px, 1.5x speed, 1.1 MB
  - [ ] Test HTTPS for the Seoul subway API from the Mac; switch `BASE` if it works
  - [ ] Rotate `MCP_ACCESS_TOKEN` now and then (it is in Cloud Run request logs via `?key=`); later, OAuth
  - [x] README draft: architecture, tools, briefing, evals, gotchas (2026-11-13)
  - [ ] README: add the final eval score (GIF added 2026-11-17)
  - [x] Repo prepared for GitHub: secret scan clean, `.gitignore` extended (BUILD_GUIDE Step 18)
  - [x] Pushed to GitHub 2026-11-13: github.com/Jay02510/seoul-commute-mcp
  - [x] Commit and push Steps 19-21 (checked 2026-11-16: `main` in sync with `origin/main`)
  - [x] Case study doc drafted (Claude Docs, 2026-11-13)

## Handoff (2026-11-15 18:20, end of chat "Seoul Commute: briefings, forecast, cloud job")
Done in that chat (2026-11-13 to 15): commute route choice (fewest transfers
within 5 min), hourly air grades, KMA 단기예보 `forecast` tool, README rewrite,
case study doc (Claude Docs), evening `home` route with per-route send times,
English station names, eval runner quota stop, cloud briefing code (Cloud Run
job), repo on GitHub (github.com/Jay02510/seoul-commute-mcp), MCP service
redeployed (revision 00006). 148 tests.
Next steps:
1. `git push` (a docs commit may be waiting locally; `git status -sb` shows "ahead").
2. Tue after 17:00 KST: eval rerun of #24 and the 4 errors (command above).
   Then put the score in README and the case study (28/33 so far).
3. Cloud briefing is live (2026-11-17). Left: `launchctl bootout`, confirm the
   first scheduled sends.
4. README GIF (`docs/demo.gif`) of the Claude.ai connector; budget alert.
5. Later: compare rules vs LLM writer; disruption alerts; Telegram two-way bot.
Redeploy the MCP service after server changes: Step 14 command.

## Handoff (2026-11-12 17:10, end of chat "Gemini LLM eval failures")
Done in that chat: eval #19 traced to '서울역' (route API keeps '역' in that
name; `find()` now retries, Step 11b); 30 s subway cache (Step 12); remote MCP
live on Cloud Run, Seoul region, project `seoul-mcp`, service
`seoul-commute-mcp`, token-protected, connected to Claude.ai (Step 13).
87 tests.
Next steps:
1. 2026-11-13 07:45: confirm the Telegram briefing (`tail logs/briefing.log` if missing).
2. When the Gemini quota resets: `uv run python -m evals.run --only 19 -v`, then
   `GEMINI_MODEL=gemini-3.5-flash uv run python -m evals.run` for the README score.
3. Budget alert in the console (Billing > Budgets & alerts, US$5, 50% and 100%).
4. README: what it is, architecture (stdio + Cloud Run), tools, eval score,
   GIF of the Claude.ai connector chat.
5. Optional: eval case for "which direction NOT to take" claims (the model added
   one from memory in the first connector test).
6. A few days of `compare work`, then `--writer llm` in the plist.
Redeploy after code changes: the `gcloud run deploy seoul-commute-mcp --source . ...`
command in BUILD_GUIDE Step 13d. Project ID is `seoul-mcp`.
Reminder: paste shell commands without trailing `# comments` (zsh passes them as arguments).

## Gotchas (README material)
- Route API: names go without '역' ('강남'), except stations whose official name includes it ('서울역'). A wrong form returns 00 with empty paths, not an error code.
- data.go.kr returns XML on auth errors even with dataType=JSON (handled in `sources/http.py`).
- KMA uses grid nx/ny, not lat/lon (`sources/districts.py`).
- KMA base_time: observations appear ~40 min after the hour; before :45 use the previous hour.
- MCP Python SDK 2.x renamed FastMCP to MCPServer (`from mcp.server.mcpserver import MCPServer`); `run(transport="stdio")`.
- Built-in browser blocks JS confirm() popups, so Korean gov sites' submit buttons silently fail.
- Seoul sign-up: use 외국인회원 path; 내국인 path rejects foreign phone verification.
- SQLite needs to delete its `-journal` file after each write. In Claude's VM, writes failed with `disk I/O error` until file deletion was approved. A leftover `briefing.db-journal` rolls back by itself on the next open on the Mac; don't delete it by hand.

## Done 2026-11-14
- [x] English station names in `next_trains` and `route` (`sources/stations.py`, BUILD_GUIDE Step 20)
- [x] Eval runner stops after 3 quota errors in a row; `--only 11-21` ranges
- [x] Redeployed MCP service (revision 00006, 2026-11-14 20:12); live check: `route('Hongik Univ. Station', 'Gangnam')` returns 홍대입구 -> 강남, 38 min, 17 stops

## Ideas backlog
- Nearest AirKorea station via 측정소정보 (getTMStdrCrdnt + getNearbyMsrstnList)
- Seoul 실시간 도시데이터 (120+ hotspots, congestion)
- Subway fare API (서울교통공사 실시간운임정보)
