import asyncio

import pytest

from conftest import load
from sources import subway
from sources.http import ApiError


def arrivals(fake_get_json, reply=None, station="홍대입구역"):
    calls = fake_get_json(subway, reply or load("subway_sample.json"))
    return asyncio.run(subway.arrivals(station)), calls


def test_parse(fake_get_json):
    trains, calls = arrivals(fake_get_json)
    assert len(trains) == 7
    assert trains[0] == {"line_id": "1002", "line": "Line 2", "direction": "성수행 - 합정방면",
                         "updown": "외선", "message": "2분 후", "seconds": 120}
    assert {t["line"] for t in trains} == {"Line 2", "Airport Railroad", "Gyeongui-Jungang"}


def test_url_strips_station_suffix_and_fetches_40_rows(fake_get_json):
    _, calls = arrivals(fake_get_json)
    url = calls[0]["url"]
    assert "/0/40/" in url
    assert url.endswith("%ED%99%8D%EB%8C%80%EC%9E%85%EA%B5%AC")   # 홍대입구, no 역


def test_no_data_is_empty_list(fake_get_json):
    trains, _ = arrivals(fake_get_json, {"errorMessage": {"code": "INFO-200", "message": "해당하는 데이터가 없습니다."}})
    assert trains == []


def test_api_error_raises(fake_get_json):
    with pytest.raises(ApiError, match="ERROR-337"):
        arrivals(fake_get_json, {"errorMessage": {"code": "ERROR-337", "message": "일일 호출 한도 초과"}})


def test_per_direction_keeps_two_per_sign(fake_get_json):
    trains, _ = arrivals(fake_get_json)
    picked = subway.per_direction(trains, 2)
    hapjeong = [t for t in picked if t["direction"].endswith("합정방면")]
    assert [t["message"] for t in hapjeong] == ["2분 후", "5분 후"]       # third one dropped
    assert any(t["direction"].endswith("신촌방면") for t in picked)      # other direction kept
    assert len(picked) == 6


def test_per_direction_groups_by_line(fake_get_json):
    trains, _ = arrivals(fake_get_json)
    lines = [t["line"] for t in subway.per_direction(trains, 1)]
    assert lines == sorted(lines, key=lines.index)   # each line's trains are together


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_cache_serves_repeat_calls(fake_get_json, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(subway, "_now", clock)
    calls = fake_get_json(subway, load("subway_sample.json"))
    first = asyncio.run(subway.arrivals("홍대입구"))
    clock.t += 10
    again = asyncio.run(subway.arrivals("홍대입구역"))     # same station, '역' stripped
    assert len(calls) == 1
    assert again[0]["seconds"] == first[0]["seconds"] - 10
    assert again[0]["message"] == first[0]["message"]


def test_cache_expires(fake_get_json, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(subway, "_now", clock)
    calls = fake_get_json(subway, load("subway_sample.json"))
    asyncio.run(subway.arrivals("홍대입구"))
    clock.t += 30
    asyncio.run(subway.arrivals("홍대입구"))
    assert len(calls) == 2


def test_cache_off_and_per_station(fake_get_json, monkeypatch):
    calls = fake_get_json(subway, load("subway_sample.json"))
    asyncio.run(subway.arrivals("홍대입구"))
    asyncio.run(subway.arrivals("강남"))
    assert len(calls) == 2                                 # different stations
    monkeypatch.setenv("SUBWAY_CACHE_SECONDS", "0")
    asyncio.run(subway.arrivals("강남"))
    assert len(calls) == 3                                 # cache off


def test_errors_not_cached(fake_get_json):
    calls = fake_get_json(subway, {"errorMessage": {"code": "ERROR-337", "message": "일일 호출 한도 초과"}})
    for _ in range(2):
        with pytest.raises(ApiError):
            asyncio.run(subway.arrivals("강남"))
    assert len(calls) == 2


def test_cached_rows_are_copies(fake_get_json):
    fake_get_json(subway, load("subway_sample.json"))
    a = asyncio.run(subway.arrivals("홍대입구"))
    a[0]["message"] = "changed"
    b = asyncio.run(subway.arrivals("홍대입구"))
    assert b[0]["message"] != "changed"
