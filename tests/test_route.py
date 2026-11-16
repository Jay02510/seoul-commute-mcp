"""sources/route.py against the real 홍대입구 -> 강남 reply and a small hand-made transfer reply."""
import asyncio

import pytest

from conftest import load
from sources import route
from sources.http import ApiError

HONGDAE = load("route_hongdae_gangnam.json")["body"]
TRANSFER = load("route_transfer_sample.json")["body"]


def test_legs_single_ride():
    parts = route.legs(HONGDAE)
    assert len(parts) == 1
    ride = parts[0]
    assert (ride["kind"], ride["line"], ride["from"], ride["to"]) == ("ride", "2호선", "홍대입구", "강남")
    assert ride["stops"] == 17               # the number the model kept getting wrong
    assert ride["toward"] == "합정"          # matches the 합정방면 sign in next_trains
    assert ride["terminus"] == "성수"


def test_legs_with_transfer():
    kinds = [p["kind"] for p in route.legs(TRANSFER)]
    assert kinds == ["ride", "transfer", "ride"]
    first, tr, second = route.legs(TRANSFER)
    assert (first["stops"], first["toward"]) == (2, "효창공원앞")
    assert tr == {"kind": "transfer", "at": "삼각지", "from_line": "6호선", "to_line": "4호선",
                  "walk_s": 180, "wait_s": 240}
    assert (second["from"], second["to"], second["stops"]) == ("삼각지", "이촌", 2)


def test_describe_hongdae():
    text = route.describe(HONGDAE)
    assert text.splitlines()[0] == ("홍대입구 -> 강남: 38 min, 17 stops, 0 transfers, card fare 1,650 won. "
                                    "Departs 11:26, arrives 12:04 (timetable).")
    assert "2호선 from 홍대입구 toward 합정, train to 성수: 17 stops to 강남" in text


def test_describe_transfer():
    text = route.describe(TRANSFER)
    assert "1 transfer," in text
    assert "Transfer at 삼각지 (6호선 to 4호선): about 3 min walk, then about 4 min wait" in text


def test_describe_empty():
    assert route.describe({"paths": []}) == "No route found."


def test_summary():
    assert route.summary(HONGDAE) == "38 min, 17 stops, no transfers (2호선 toward 합정; timetable 11:26-12:04)"
    assert route.summary(TRANSFER) == ("15 min, 4 stops, change at 삼각지 (6호선 to 4호선) "
                                       "(6호선 toward 효창공원앞; timetable 08:00-08:15)")
    assert route.summary({"paths": []}) == "no route found"


def test_first_toward():
    assert route.first_toward(HONGDAE) == "합정"
    assert route.first_toward({"paths": []}) is None


def test_find_params(fake_get_json):
    calls = fake_get_json(route, load("route_hongdae_gangnam.json"))
    body = asyncio.run(route.find("홍대입구역", " 강남 ", prefer="fewest_transfers"))
    assert body["totalReqHr"] == 2280
    p = calls[0]["params"]
    assert (p["dptreStn"], p["arvlStn"], p["searchType"]) == ("홍대입구", "강남", "transfer")
    assert len(p["searchDt"]) == 19          # yyyy-MM-dd HH:mm:ss


@pytest.mark.parametrize("code, message", [("10", "unknown station name"), ("99", "route server error")])
def test_find_error_codes(fake_get_json, code, message):
    fake_get_json(route, {"header": {"resultCode": code, "resultMsg": "x"}})
    with pytest.raises(ApiError, match=message):
        asyncio.run(route.find("없는역", "강남"))


def test_find_retries_with_yeok(monkeypatch):
    """서울역 keeps '역' in its official name: '서울' gives 00 with no paths."""
    good = load("route_hongdae_gangnam.json")
    sent = []

    async def fake(url, params=None):
        sent.append((params["dptreStn"], params["arvlStn"]))
        return good if params["dptreStn"] == "서울역" else {"header": {"resultCode": "00"}, "body": {"paths": []}}

    monkeypatch.setattr(route, "get_json", fake)
    body = asyncio.run(route.find("서울역", "강남"))
    assert body["paths"]
    assert sent == [("서울", "강남"), ("서울역", "강남")]


def test_find_no_paths_anywhere(fake_get_json):
    calls = fake_get_json(route, {"header": {"resultCode": "00"}, "body": {"paths": []}})
    with pytest.raises(ApiError, match="did not match"):
        asyncio.run(route.find("없는곳", "강남"))
    assert len(calls) == 4


def test_find_empty_body(fake_get_json):
    fake_get_json(route, {"header": {"resultCode": "00"}, "body": None})
    with pytest.raises(ApiError, match="empty reply"):
        asyncio.run(route.find("홍대입구", "강남"))


def test_describe_gives_minutes_per_ride():
    """Eval #24: the model computed a ride time from timetable times; the tool now states it."""
    import re
    from conftest import load
    from sources import route as r
    for name in ("route_hongdae_gangnam.json", "route_transfer_sample.json"):
        text = r.describe(load(name)["body"])
        rides = [ln for ln in text.splitlines() if ln.startswith("- ") and "Transfer" not in ln]
        assert rides and all(re.search(r", \d+ min \(\d\d:\d\d-\d\d:\d\d\)$", ln) for ln in rides), text

