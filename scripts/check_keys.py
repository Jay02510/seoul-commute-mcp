"""Smoke test: call each API once, print OK or the exact error.

Run:  uv run python scripts/check_keys.py
Exits 1 if any API fails. Also run as a Cloud Run job to check the APIs answer from Google's servers
(BUILD_GUIDE Step 13).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for `sources`
import asyncio

from sources import airkorea, kma, route, subway


async def check(name, coro):
    try:
        result = await coro
        print(f"OK    {name}\n      {result}\n")
        return True
    except Exception as e:  # show everything in a smoke test
        print(f"FAIL  {name}\n      {type(e).__name__}: {e}\n")
        return False


async def _route():
    return route.summary(await route.find("홍대입구", "강남"))


async def main() -> bool:
    results = [
        await check("KMA weather (Mapo)", kma.current("Mapo")),
        await check("AirKorea air (Mapo)", airkorea.current("Mapo")),
        await check("Subway arrivals (Gangnam)", subway.arrivals("강남", n=3)),
        await check("Subway route (홍대입구 -> 강남)", _route()),
    ]
    return all(results)


if __name__ == "__main__":
    # Exit 1 if any API failed, so a Cloud Run probe job shows as failed
    # instead of "successfully completed".
    sys.exit(0 if asyncio.run(main()) else 1)
