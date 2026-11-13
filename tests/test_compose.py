"""Rules writer: every part is shown or marked unavailable, never silently dropped."""
import asyncio
from datetime import datetime

import pytest

from briefing import compose as c
from conftest import load
from sources.http import ApiError

NOW = datetime(2026, 11, 12, 7, 45)
ROUTE = {"name": "work", "home": "마포구", "work": "강남구", "station": "홍대입구", "toward": "합정", "dest": ""}
JOURNEY = load("route_hongdae_gangnam.json")["body"]


def weather(temp=15.0, precip="none", rain=0.0, wind=2.0, district="마포구"):
    return {"district": district, "observed": "20261112 0700", "temp_c": temp, "rain_mm_1h": rain,
            "precip": precip, "humidity_pct": 60, "wind_ms": wind}


def air(station="마포구", pm25="20", g25="moderate", pm10="30", g10="good"):
    return {"station": station, "measured": "2026-11-12 07:00", "pm10": pm10, "pm10_grade": g10,
            "pm25": pm25, "pm25_grade": g25}


TRAINS = [
    {"line": "Line 2", "direction": "성수행 - 합정방면", "message": "2분 후"},
    {"line": "Line 2", "direction": "성수행 - 신촌방면", "message": "전역 도착"},
]


def data(**over):
    d = {"weather_home": weather(), "weather_work": weather(district="강남구"),
         "air_home": air(), "air_work": air("강남구"), "trains": TRAINS}
    d.update(over)
    return d


def test_calm_day():
    text = c.compose(ROUTE, data(), NOW)
    assert text.splitlines()[0] == "🚇 work: Mapo → Gangnam · Thu 07:45"
    assert "Weather: Mapo 15.0°C, Gangnam 15.0°C, dry" in text
    assert "• [Line 2] 2분 후" in text and "전역 도착" not in text    # filtered to 합정
    assert text.endswith("✅ No umbrella or mask needed.")
    assert "Journey" not in text                                       # no dest saved


def test_missing_ends_never_reassure():
    text = c.compose(ROUTE, data(weather_work=ApiError("KMA 03: NO_DATA"),
                                 air_home=ApiError("x" * 300)), NOW)
    assert "Gangnam unavailable" in text and "dry in Mapo" in text
    assert "Air: Mapo unavailable, Gangnam PM2.5 20" in text
    assert "⚠️ No data for Gangnam weather, Mapo air" in text
    assert "✅" not in text
    assert "x" * 61 not in text                                        # long errors cut


def test_rain_at_work_and_cold_end():
    text = c.compose(ROUTE, data(weather_work=weather(3.0, "rain", 1.5, district="강남구")), NOW)
    assert "rain now in Gangnam" in text
    assert "☔ Rain now in Gangnam (1.5 mm last hour). Take an umbrella." in text
    assert "🧥 Cold: warm coat." in text                               # from the colder end


def test_unknown_air_grade_blocks_reassurance():
    text = c.compose(ROUTE, data(air_home=air(pm25="-", g25="n/a")), NOW)
    assert "✅" not in text
    assert "⚠️ No data for Mapo air grade" in text


def test_bad_air_mask():
    text = c.compose(ROUTE, data(air_work=air("강남구", "60", "bad")), NOW)
    assert "😷 Wear a mask: Gangnam PM2.5 60 (bad)" in text


def test_total_outage():
    err = ApiError("down")
    text = c.compose(ROUTE, {k: err for k in data()}, NOW)
    assert "Weather: unavailable (down)" in text
    assert "Air: unavailable (down)" in text
    assert "Trains at 홍대입구: unavailable (down)" in text
    assert "✅" not in text


def test_journey_line():
    text = c.compose({**ROUTE, "dest": "강남"}, data(journey=JOURNEY), NOW)
    assert "Journey to 강남: 38 min, 17 stops, no transfers (2호선 toward 합정; timetable 11:26-12:04)" in text
    assert "⚠️" not in text                                            # direction matches


def test_journey_direction_mismatch():
    text = c.compose({**ROUTE, "dest": "강남", "toward": "신촌"}, data(journey=JOURNEY), NOW)
    assert "⚠️ Suggested route boards toward 합정, not 신촌" in text


def test_journey_failed_keeps_weather_reassurance():
    text = c.compose({**ROUTE, "dest": "강남"}, data(journey=ApiError("Route: unknown station name")), NOW)
    assert "Journey to 강남: unavailable (Route: unknown station name)" in text
    assert "✅ No umbrella or mask needed." in text                    # weather and air were all checked
    assert "⚠️ No data for journey" in text


def test_gather_adds_journey_only_with_dest(monkeypatch):
    calls = []

    async def ok(*args, **kw):
        calls.append(args)
        return {}

    async def boom(*args, **kw):
        raise ApiError("route down")

    for mod, fn in [(c.kma, "current"), (c.kma, "forecast"), (c.airkorea, "current"), (c.subway, "arrivals")]:
        monkeypatch.setattr(mod, fn, ok)
    monkeypatch.setattr(c.routes, "find", boom)

    without = asyncio.run(c.gather(ROUTE))
    assert "journey" not in without and len(without) == 7

    with_dest = asyncio.run(c.gather({**ROUTE, "dest": "강남"}))
    assert isinstance(with_dest["journey"], ApiError)                  # failure is a value, not a crash
    assert with_dest["trains"] == {}
