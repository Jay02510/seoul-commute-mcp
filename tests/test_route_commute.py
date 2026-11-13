"""Commute route choice: fewer transfers unless the fastest route saves real time."""
import asyncio
import copy

import pytest

from conftest import load
from sources import route as r
from sources.http import ApiError

DIRECT = load("route_hongdae_gangnam.json")["body"]      # 38 min, 0 transfers, 2호선 toward 합정
TRANSFER = load("route_transfer_sample.json")["body"]    # 1 transfer, boards toward 효창공원앞 side


def variant(body, minutes, transfers=None):
    b = copy.deepcopy(body)
    b["totalReqHr"] = minutes * 60
    if transfers is not None:
        b["trsitNmtm"] = transfers
    return b


def test_fewer_transfers_wins_when_fastest_saves_little():
    fast = variant(TRANSFER, 36, transfers=2)             # the 2026-11-13 case: 2 min saved, 2 changes
    assert r.pick_commute([fast, DIRECT]) is DIRECT


def test_fastest_wins_when_it_saves_more_than_slack():
    fast = variant(TRANSFER, 30, transfers=1)             # 8 min faster
    assert r.pick_commute([fast, DIRECT]) is fast


def test_saved_direction_beats_transfer_count_within_slack():
    other = variant(TRANSFER, 37, transfers=0)            # same transfers, wrong direction
    assert r.pick_commute([other, DIRECT], toward="합정") is DIRECT
    assert r.pick_commute([DIRECT, other], toward=r.first_toward(other)) is other


def test_empty_replies_raise():
    with pytest.raises(ApiError):
        r.pick_commute([{}, {"paths": []}])


def test_commute_uses_whichever_search_works(monkeypatch):
    async def find(src, dst, prefer="fastest", when=None):
        if prefer == "fastest":
            raise ApiError("route down")
        return DIRECT

    monkeypatch.setattr(r, "find", find)
    assert asyncio.run(r.commute("홍대입구", "강남", "합정")) is DIRECT


def test_commute_raises_when_both_fail(monkeypatch):
    async def find(*a, **kw):
        raise ApiError("route down")

    monkeypatch.setattr(r, "find", find)
    with pytest.raises(ApiError):
        asyncio.run(r.commute("홍대입구", "강남"))
