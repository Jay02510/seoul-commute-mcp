"""Shared test setup.

Every test runs offline: fake API keys, and any real HTTP request fails the
test. Sources are tested by replacing their `get_json` with a fake that
returns a recorded reply from tests/fixtures/.
"""
import json
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "test-data-go-kr-key")
    monkeypatch.setenv("SEOUL_API_KEY", "test-seoul-key")

    async def no_network(self, request):
        raise AssertionError(f"Test tried a real HTTP request: {request.method} {request.url.host}")

    # Block the real network transport only; httpx.MockTransport still works.
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)

    # The subway cache lives at module level; start every test with it empty.
    from sources import subway
    subway.clear_cache()


@pytest.fixture
def fake_get_json(monkeypatch):
    """fake_get_json(module, reply) makes module.get_json return `reply` and
    records each call's url and params in the returned list."""
    def install(module, reply):
        calls = []

        async def fake(url, params=None):
            calls.append({"url": url, "params": params or {}})
            return reply

        monkeypatch.setattr(module, "get_json", fake)
        return calls
    return install
