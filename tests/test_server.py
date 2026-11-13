"""MCP tool functions: errors come back as text, guardrails are in the results."""
import asyncio

import server
from conftest import load
from sources import route, subway
from sources.http import ApiError


def run(coro):
    return asyncio.run(coro)


def test_list_districts():
    text = server.list_districts()
    assert "Mapo (마포구)" in text and text.count("(") == 25


def test_route_tool(fake_get_json):
    fake_get_json(route, load("route_hongdae_gangnam.json"))
    text = run(server.route("홍대입구", "강남"))
    assert text.startswith("홍대입구 -> 강남: 38 min, 17 stops")


def test_route_tool_error_is_text(fake_get_json):
    fake_get_json(route, {"header": {"resultCode": "10"}})
    assert run(server.route("없음", "강남")).startswith("Error: Route 없음 -> 강남: unknown station name")


def test_next_trains_guardrail_and_clamp(fake_get_json):
    fake_get_json(subway, load("subway_sample.json"))
    text = run(server.next_trains("홍대입구역", per_direction=99))   # clamped to 3
    assert text.startswith("Next trains at 홍대입구:")
    assert text.count("합정방면") == 3
    assert "never estimate them from memory" in text


def test_next_trains_no_data(fake_get_json):
    fake_get_json(subway, {"errorMessage": {"code": "INFO-200"}})
    assert "No arrival data for '없음'" in run(server.next_trains("없음"))


def test_missing_key_is_text(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_KEY")
    assert "DATA_GO_KR_KEY is missing" in run(server.air_quality("Mapo"))


def test_route_error_carries_no_memory_rule(fake_get_json):
    fake_get_json(route, {"header": {"resultCode": "99"}})
    text = run(server.route("홍대입구", "강남"))
    assert text.startswith("Error:") and "do not give stop counts" in text


def test_eval_fail_outage(monkeypatch):
    monkeypatch.setattr(server, "EVAL_FAIL", {"route", "air_quality"})
    assert run(server.air_quality("Mapo")) == server.OUTAGE
    assert run(server.route("홍대입구", "강남")).startswith(server.OUTAGE + "\nNo route data")
