import asyncio
import copy
from datetime import datetime

import pytest

from conftest import load
from sources import airkorea, kma
from sources.http import ApiError


@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 11, 12, 7, 44), ("20261112", "0600")),   # before :45, previous hour
    (datetime(2026, 11, 12, 7, 45), ("20261112", "0700")),
    (datetime(2026, 11, 13, 0, 10), ("20261112", "2300")),   # crosses midnight
])
def test_latest_base(now, expected):
    assert kma.latest_base(now) == expected


def test_kma_parse(fake_get_json):
    calls = fake_get_json(kma, load("kma_sample.json"))
    w = asyncio.run(kma.current("Mapo"))
    assert w == {"district": "마포구", "observed": w["observed"], "temp_c": 9.5, "rain_mm_1h": 0.0,
                 "precip": "none", "humidity_pct": 60, "wind_ms": 2.1}
    p = calls[0]["params"]
    assert (p["nx"], p["ny"]) == (59, 127)          # grid, not lat/lon
    assert p["serviceKey"] == "test-data-go-kr-key"


def test_kma_rain(fake_get_json):
    reply = load("kma_sample.json")
    for item in reply["response"]["body"]["items"]["item"]:
        if item["category"] == "PTY":
            item["obsrValue"] = "1"
        if item["category"] == "RN1":
            item["obsrValue"] = "2.5"
    fake_get_json(kma, reply)
    w = asyncio.run(kma.current("Mapo"))
    assert (w["precip"], w["rain_mm_1h"]) == ("rain", 2.5)


def test_kma_error_code(fake_get_json):
    reply = load("kma_sample.json")
    reply["response"]["header"] = {"resultCode": "03", "resultMsg": "NO_DATA"}
    fake_get_json(kma, reply)
    with pytest.raises(ApiError, match="KMA 03"):
        asyncio.run(kma.current("Mapo"))


def test_airkorea_parse(fake_get_json):
    calls = fake_get_json(airkorea, load("airkorea_sample.json"))
    a = asyncio.run(airkorea.current("mapo"))
    assert a == {"station": "마포구", "measured": "2026-11-12 07:00", "pm10": "41",
                 "pm10_grade": "moderate", "pm25": "23", "pm25_grade": "moderate"}
    assert calls[0]["params"]["stationName"] == "마포구"


def test_airkorea_missing_grade(fake_get_json):
    reply = load("airkorea_sample.json")
    row = reply["response"]["body"]["items"][0]
    row["pm25Value"], row["pm25Grade"] = "-", None              # station offline for PM2.5
    fake_get_json(airkorea, reply)
    assert asyncio.run(airkorea.current("Mapo"))["pm25_grade"] == "n/a"


def test_airkorea_grade_from_hourly_value(fake_get_json):
    reply = load("airkorea_sample.json")
    row = reply["response"]["body"]["items"][0]
    row["pm25Value"], row["pm25Grade"] = "39", "2"              # 24h grade says moderate, hour is bad
    fake_get_json(airkorea, reply)
    assert asyncio.run(airkorea.current("Mapo"))["pm25_grade"] == "bad"


@pytest.mark.parametrize("kind,value,expected", [
    ("pm25", "15", "good"), ("pm25", "16", "moderate"), ("pm25", "35", "moderate"),
    ("pm25", "36", "bad"), ("pm25", "76", "very bad"),
    ("pm10", "30", "good"), ("pm10", "81", "bad"), ("pm10", "151", "very bad"),
])
def test_grade_bands(kind, value, expected):
    assert airkorea.grade(kind, value) == expected


def test_grade_falls_back_to_api_grade_without_a_number():
    assert airkorea.grade("pm25", "-", "3") == "bad"
    assert airkorea.grade("pm25", None, None) == "n/a"


def test_airkorea_no_rows(fake_get_json):
    reply = load("airkorea_sample.json")
    reply["response"]["body"]["items"] = []
    fake_get_json(airkorea, reply)
    with pytest.raises(ApiError, match="No air data"):
        asyncio.run(airkorea.current("Mapo"))
