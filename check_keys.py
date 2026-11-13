"""Smoke test: call each API once, print OK or the exact error.

Run:  uv run check_keys.py
Also run as a Cloud Run job to check the APIs answer from Google's servers
(BUILD_GUIDE Step 13).
"""
import asyncio

from sources import airkorea, kma, route, subway


async def check(name, coro):
    try:
        result = await coro
        print(f"OK    {name}\n      {result}\n")
    except Exception as e:  # show everything in a smoke test
        print(f"FAIL  {name}\n      {type(e).__name__}: {e}\n")


async def _route():
    return route.summary(await route.find("홍대입구", "강남"))


async def main():
    await check("KMA weather (Mapo)", kma.current("Mapo"))
    await check("AirKorea air (Mapo)", airkorea.current("Mapo"))
    await check("Subway arrivals (Gangnam)", subway.arrivals("강남", n=3))
    await check("Subway route (홍대입구 -> 강남)", _route())


if __name__ == "__main__":
    asyncio.run(main())
