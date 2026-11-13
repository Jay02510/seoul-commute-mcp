"""KMA 단기예보: base time, parsing, rain detection, briefing line, MCP tool.
Uses a synthetic fixture (rain 18:00-20:00) until a live reply is recorded."""
import asyncio
import copy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import server
from briefing import compose as c
from conftest import load
from sources import kma
from sources.http import ApiError

KST = ZoneInfo("Asia/Seoul")
AT_0745 = datetime(2026, 11, 12, 7, 45, tzinfo=KST)
SAMPLE = load("kma_forecast_sample.json")


@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 11, 12, 7, 45), ("20261112", "0500")),
    (datetime(2026, 11, 12, 8, 14), ("20261112", "0500")),   # 08:00 issue not online yet
    (datetime(2026, 11, 12, 8, 15), ("20261112", "0800")),
    (datetime(2026, 11, 13, 2, 0), ("20261112", "2300")),    # before 02:15: yesterday 23:00
    (datetime(2026, 11, 13, 0, 5), ("20261112", "2300")),
])
def test_forecast_base(now, expected):
    assert kma.forecast_base(now) == expected


def test_forecast_parse(fake_get_json):
    calls = fake_get_json(kma, copy.deepcopy(SAMPLE))
    fc = asyncio.run(kma.forecast("Mapo", 12, now=AT_0745))
    assert fc["district"] == "마포구" and fc["issued"] == "20261112 0500"
    assert [h["time"] for h in fc["hours"]][:2] == ["07:00", "08:00"]   # starts at the current hour
    assert len(fc["hours"]) == 12 and fc["hours"][-1]["time"] == "18:00"
    p = calls[0]["params"]
    assert (p["nx"], p["ny"], p["base_time"]) == (59, 127, "0500")


def test_wet_hours_finds_evening_rain(fake_get_json):
    fake_get_json(kma, copy.deepcopy(SAMPLE))
    fc = asyncio.run(kma.forecast("Mapo", 24, now=AT_0745))
    wet = kma.wet_hours(fc)
    assert [h["time"] for h in wet] == ["18:00", "19:00", "20:00"]
    assert wet[0]["precip"] == "rain" and wet[0]["pop"] == 70


def test_hours_clamped(fake_get_json):
    fake_get_json(kma, copy.deepcopy(SAMPLE))
    assert len(asyncio.run(kma.forecast("Mapo", 99, now=AT_0745))["hours"]) == 23   # fixture ends 05:00
    fake_get_json(kma, copy.deepcopy(SAMPLE))
    assert len(asyncio.run(kma.forecast("Mapo", 0, now=AT_0745))["hours"]) == 1


def test_forecast_error_code(fake_get_json):
    reply = copy.deepcopy(SAMPLE)
    reply["response"]["header"] = {"resultCode": "03", "resultMsg": "NO_DATA"}
    fake_get_json(kma, reply)
    with pytest.raises(ApiError, match="KMA forecast 03"):
        asyncio.run(kma.forecast("Mapo", now=AT_0745))


# Briefing

def fc(times_wet=(), until="19:00", pop=70):
    hours = [{"date": "20261112", "time": f"{h:02d}:00", "temp_c": 12.0,
              "pop": pop if f"{h:02d}:00" in times_wet else 10,
              "precip": "rain" if f"{h:02d}:00" in times_wet else "none", "pcp": "강수없음"}
             for h in range(8, int(until[:2]) + 1)]
    return {"district": "x", "issued": "20261112 0500", "hours": hours}


from test_compose import NOW, ROUTE, data  # noqa: E402


def test_dry_forecast_keeps_reassurance():
    text = c.compose(ROUTE, data(forecast_home=fc(), forecast_work=fc()), NOW)
    assert "Later: no rain expected until 19:00" in text
    assert "✅ No umbrella or mask needed." in text


def test_rain_later_adds_umbrella():
    text = c.compose(ROUTE, data(forecast_home=fc(), forecast_work=fc(("18:00",))), NOW)
    assert "Later: rain likely from 18:00 in Gangnam (70%)" in text
    assert "☂️ Take an umbrella for later (18:00)." in text
    assert "✅" not in text


def test_failed_forecast_blocks_reassurance():
    text = c.compose(ROUTE, data(forecast_home=ApiError("KMA forecast 03"), forecast_work=fc()), NOW)
    assert "Later: no rain expected in Gangnam until 19:00" in text
    assert "⚠️ No data for Mapo forecast" in text
    assert "✅" not in text


def test_both_forecasts_failed():
    e = ApiError("down")
    text = c.compose(ROUTE, data(forecast_home=e, forecast_work=e), NOW)
    assert "Later: forecast unavailable (down)" in text


# MCP tool

def test_forecast_tool(fake_get_json, monkeypatch):
    real = kma.forecast
    monkeypatch.setattr(kma, "forecast", lambda d, h=12: real(d, h, now=AT_0745))
    fake_get_json(kma, copy.deepcopy(SAMPLE))
    out = asyncio.run(server.forecast("Mapo", 24))
    assert out.startswith("마포구 forecast (KMA issue 20261112 0500 KST). Rain likely from 18:00.")
    assert "- 18:00:" in out and "rain chance 70%" in out


def test_forecast_tool_outage(monkeypatch):
    monkeypatch.setattr(server, "EVAL_FAIL", {"forecast"})
    assert asyncio.run(server.forecast("Mapo")) == server.OUTAGE
