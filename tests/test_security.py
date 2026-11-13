"""Input limits, URL encoding and secret redaction (security review 2026-11-12)."""
import asyncio

import httpx
import pytest

import server
from sources import subway
from sources.http import MAX_NAME, check_name


def test_check_name_trims_and_rejects():
    assert check_name(" 강남역 ") == "강남"
    with pytest.raises(ValueError):
        check_name("   ")
    with pytest.raises(ValueError):
        check_name("가" * (MAX_NAME + 1))


def test_station_slash_is_encoded(monkeypatch):
    """A '/' in the name must not change the Seoul API path (no ../ traversal)."""
    seen = {}

    async def fake_get_json(url, params=None):
        seen["url"] = url
        return {"errorMessage": {"code": "INFO-200"}}

    monkeypatch.setenv("SEOUL_API_KEY", "testkey")
    monkeypatch.setattr(subway, "get_json", fake_get_json)
    subway.clear_cache()
    asyncio.run(subway.arrivals("../../x"))
    path = seen["url"].split("realtimeStationArrival/0/")[1]
    assert "/" not in path.split("/", 1)[1]
    assert "..%2F..%2Fx" in seen["url"]


def test_errors_redact_keys(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "SECRETKEY123456")
    msg = server._err(ValueError("upstream said SECRETKEY123456 is bad"))
    assert "SECRETKEY123456" not in msg and "[redacted]" in msg


def test_network_errors_are_generic(monkeypatch):
    monkeypatch.setenv("SEOUL_API_KEY", "SEOULKEY987654")
    e = httpx.ConnectError("failed http://x/api/subway/SEOULKEY987654/json")
    msg = server._err(e)
    assert "SEOULKEY987654" not in msg and "http://" not in msg


def test_next_trains_rejects_long_name():
    out = asyncio.run(server.next_trains("가" * 100))
    assert out.startswith("Error:") and "too long" in out
