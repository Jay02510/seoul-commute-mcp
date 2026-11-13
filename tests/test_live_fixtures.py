"""Parsers against real replies saved by tests/record_fixtures.py.
Skipped until that script has been run on the Mac. Checks shape, not values."""
import asyncio

import pytest

from conftest import FIXTURES, load
from sources import airkorea, kma, route, subway

LIVE = FIXTURES / "live"


def live(name):
    if not (LIVE / f"{name}.json").exists():
        pytest.skip(f"no live/{name}.json yet: run `uv run python tests/record_fixtures.py`")
    return load(f"live/{name}.json")


def test_live_kma(fake_get_json):
    fake_get_json(kma, live("kma"))
    w = asyncio.run(kma.current("Mapo"))
    assert -30 < w["temp_c"] < 45 and w["precip"] != "unknown"


def test_live_kma_forecast(fake_get_json):
    fake_get_json(kma, live("kma_forecast"))
    from datetime import datetime
    from zoneinfo import ZoneInfo
    items = live("kma_forecast")["response"]["body"]["items"]["item"]
    first = min(i["fcstDate"] + i["fcstTime"] for i in items)
    now = datetime.strptime(first, "%Y%m%d%H%M").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    fc = asyncio.run(kma.forecast("Mapo", 12, now=now))
    assert fc["hours"] and all(0 <= h["pop"] <= 100 and h["precip"] != "unknown" for h in fc["hours"])


def test_live_airkorea(fake_get_json):
    fake_get_json(airkorea, live("airkorea"))
    a = asyncio.run(airkorea.current("Mapo"))
    assert a["station"] == "마포구" and a["measured"]


def test_live_subway(fake_get_json):
    fake_get_json(subway, live("subway"))
    trains = asyncio.run(subway.arrivals("홍대입구"))
    assert all(t["line"] and t["message"] is not None for t in trains)
    assert not any(t["line"].startswith("line ") for t in trains)   # every subwayId has a name


def test_live_route():
    body = live("route")["body"]
    rides = [p for p in route.legs(body) if p["kind"] == "ride"]
    assert rides[0]["from"] == "공덕" and rides[-1]["to"] == "강남"
    assert route.summary(body).count("change at") == (1 if body["trsitNmtm"] else 0)
