"""Morning briefing CLI.

  uv run -m briefing.main add-route work --home Mapo --work Gangnam --station 홍대입구 --toward 합정 --to 강남
  uv run -m briefing.main add-route home --home Gangnam --work Mapo --station 강남 --toward 교대 --to 홍대입구 --at 18:00
  uv run -m briefing.main set-dest work 강남  # add a journey line to an existing route ('' clears)
  uv run -m briefing.main set-time home 18:00 # change a route's send time
  uv run -m briefing.main list
  uv run -m briefing.main preview [work]      # print, don't send
  uv run -m briefing.main preview work --writer llm -v   # LLM writer, show tool calls
  uv run -m briefing.main compare work        # rules and LLM output side by side
  uv run -m briefing.main run [--force]       # send due routes to Telegram (used by launchd)
  uv run -m briefing.main run --routes-file deploy/routes.json   # cloud job: routes from JSON, no database
  uv run -m briefing.main chat-id             # find your Telegram chat id
  uv run -m briefing.main remove work
"""
import argparse
import asyncio
import sys
from datetime import datetime

from . import store, telegram
from .compose import compose, gather

async def _build_rules(route) -> str:
    return compose(route, await gather(route))


async def _build(route, writer: str = "rules", verbose: bool = False) -> str:
    """Write the briefing. The LLM writer falls back to rules on any failure
    (no key, API down, quota hit, bad output), so the morning message always arrives."""
    if writer == "llm":
        from . import llm  # lazy: rules mode shouldn't need the LLM SDKs
        try:
            return await llm.write(route, verbose=verbose)
        except Exception as e:
            print(f"{datetime.now():%F %T} LLM writer failed, using rules: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
    return await _build_rules(route)


async def cmd_run(force: bool, writer: str, routes_file: str | None = None) -> int:
    now = store.kst_now()
    if routes_file:
        # Cloud job (BUILD_GUIDE Step 21): no database, so no send log. Cloud
        # Scheduler fires once per slot and the job never retries, so each
        # route is still sent once; the send window picks morning vs evening.
        con = None
        routes = store.load_routes_file(routes_file)
        routes = routes if force else [r for r in routes if store.in_window(r, now)]
    else:
        con = store.connect()
        # Each route has its own send time; due_routes() also skips stale ones
        # (more than store.LATE_WINDOW late, e.g. the Mac woke at noon).
        routes = store.list_routes(con) if force else store.due_routes(con, now)
    if not routes:
        print(f"{now:%F %T} nothing due")
        return 0
    failures = 0
    for r in routes:
        try:
            text = await _build(r, writer)
            await telegram.send(text)
            if con is not None:
                store.mark_sent(con, r["id"], now.date())
            print(f"{now:%F %T} sent {r['name']}")
        except Exception as e:  # keep going for other routes; launchd log shows it
            failures += 1
            print(f"{now:%F %T} FAIL {r['name']}: {type(e).__name__}: {e}", file=sys.stderr)
    return 1 if failures else 0


async def cmd_preview(name: str | None, writer: str, verbose: bool) -> int:
    con = store.connect()
    routes = [store.get_route(con, name)] if name else store.list_routes(con)
    routes = [r for r in routes if r]
    if not routes:
        print("No routes. Add one with add-route.")
        return 1
    for r in routes:
        print(await _build(r, writer, verbose), end="\n\n")
    return 0


async def cmd_compare(name: str) -> int:
    from . import llm
    route = store.get_route(store.connect(), name)
    if not route:
        print(f"No route {name!r}.")
        return 1
    # LLM first: on the Mac, running the rules fetch first in the same process
    # made the MCP server launch fail ("Connection closed"); under investigation.
    print("── llm " + "─" * 32)
    ok = True
    try:
        print(await llm.write(route, verbose=True))
    except Exception as e:
        print(f"(LLM failed: {type(e).__name__}: {e})  see logs/mcp-server.log")
        ok = False
    print("\n── rules " + "─" * 30)
    print(await _build_rules(route))
    return 0 if ok else 1


async def cmd_chat_id() -> int:
    try:
        chats = await telegram.chat_ids()
    except Exception as e:
        print(f"Error: {e}")
        return 1
    if not chats:
        print("No chats yet. Open your bot in Telegram, send it any message, then rerun.")
        return 1
    for cid, who in chats:
        print(f"{cid}\t{who}")
    print("\nPut the number in .env as TELEGRAM_CHAT_ID=...")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="briefing")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add-route", help="save a commute route")
    a.add_argument("name")
    a.add_argument("--home", required=True, help="start district, e.g. Mapo")
    a.add_argument("--work", required=True, help="destination district, e.g. Gangnam")
    a.add_argument("--station", required=True, help="boarding station in Korean, e.g. 홍대입구")
    a.add_argument("--toward", default="", help="direction keyword from the train sign, e.g. 합정")
    a.add_argument("--days", default="mon,tue,wed,thu,fri")
    a.add_argument("--to", default="", help="destination station in Korean, e.g. 강남 (adds a journey line)")
    a.add_argument("--at", default="07:45", help="send time HH:MM (default 07:45); launchd must fire then")
    st = sub.add_parser("set-time", help="change a route's send time")
    st.add_argument("name")
    st.add_argument("at", help="HH:MM, e.g. 18:00")
    sd = sub.add_parser("set-dest", help="set or clear a route's destination station")
    sd.add_argument("name")
    sd.add_argument("station", help="Korean station name, e.g. 강남; '' to clear")

    sub.add_parser("list", help="show saved routes")
    r = sub.add_parser("remove", help="delete a route")
    r.add_argument("name")
    pv = sub.add_parser("preview", help="print briefing without sending")
    pv.add_argument("name", nargs="?")
    rn = sub.add_parser("run", help="send due briefings to Telegram")
    rn.add_argument("--force", action="store_true", help="ignore day, time and send log")
    rn.add_argument("--routes-file", help="read routes from this JSON file instead of briefing.db (cloud job)")
    for sp in (pv, rn):
        sp.add_argument("--writer", choices=["rules", "llm"], default="rules",
                        help="rules (default) or llm (falls back to rules on failure)")
    pv.add_argument("-v", "--verbose", action="store_true", help="print the LLM's tool calls")
    cp = sub.add_parser("compare", help="print rules and LLM briefings side by side")
    cp.add_argument("name")
    sub.add_parser("chat-id", help="find your Telegram chat id")

    args = p.parse_args()
    if args.cmd == "add-route":
        con = store.connect()
        try:
            store.add_route(con, args.name, args.home, args.work, args.station, args.toward,
                            args.days, dest=args.to, at=args.at)
        except Exception as e:
            print(f"Error: {e}")
            return 1
        print(f"Saved route {args.name!r}.")
        return 0
    if args.cmd == "list":
        rows = store.list_routes(store.connect())
        for x in rows:
            print(f"{x['name']}: {x['home']} → {x['work']}, board {x['station']}"
                  f"{' toward ' + x['toward'] if x['toward'] else ''}"
                  f"{', ride to ' + store.dest(x) if store.dest(x) else ''}, {x['days']} at {store.send_time(x)}"
                  f"{'' if x['active'] else ' (inactive)'}")
        if not rows:
            print("No routes yet.")
        return 0
    if args.cmd == "set-dest":
        ok = store.set_dest(store.connect(), args.name, args.station)
        print(("Cleared destination." if not args.station.strip() else f"Destination set to {args.station}.")
              if ok else "No such route.")
        return 0 if ok else 1
    if args.cmd == "set-time":
        try:
            ok = store.set_time(store.connect(), args.name, args.at)
        except ValueError as e:
            print(f"Error: {e}")
            return 1
        print(f"Send time set to {args.at}." if ok else "No such route.")
        return 0 if ok else 1
    if args.cmd == "remove":
        ok = store.remove_route(store.connect(), args.name)
        print("Removed." if ok else "No such route.")
        return 0 if ok else 1
    if args.cmd == "preview":
        return asyncio.run(cmd_preview(args.name, args.writer, args.verbose))
    if args.cmd == "run":
        return asyncio.run(cmd_run(args.force, args.writer, args.routes_file))
    if args.cmd == "compare":
        return asyncio.run(cmd_compare(args.name))
    if args.cmd == "chat-id":
        return asyncio.run(cmd_chat_id())
    return 1


if __name__ == "__main__":
    sys.exit(main())
