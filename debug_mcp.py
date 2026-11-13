"""Diagnostic: talk to server.py over MCP exactly like briefing/llm.py does,
but with no model involved. Prints each step with a timestamp.

    uv run python debug_mcp.py
"""
import asyncio
import sys
import traceback
from datetime import datetime

from mcp import Client

from briefing.llm import server_params, result_text


def say(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


async def main():
    say(f"python: {sys.executable}")
    async with Client(server_params()) as c:
        say("connected; tools: " + ", ".join(t.name for t in (await c.list_tools()).tools))
        calls = [("current_weather", {"district": "Mapo"}), ("air_quality", {"district": "Gangnam"}),
                 ("next_trains", {"station": "홍대입구"})]
        for name, args in calls:
            say(f"→ {name}{args}")
            r = await c.call_tool(name, args)
            say(f"← {result_text(r)[:120]!r}")
        say("idle 15s (like waiting for the model)...")
        await asyncio.sleep(15)
        r = await c.call_tool("list_districts", {})
        say(f"after idle: {result_text(r)[:60]!r}")
        say("closing")
    say("closed cleanly: MCP side is fine")


try:
    asyncio.run(main())
except BaseException:
    say("FAILED:")
    traceback.print_exc()
