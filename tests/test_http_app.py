"""Remote MCP over HTTP: token gate, health check, a real tools/list."""
import pytest
from starlette.testclient import TestClient

import http_app

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}}}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MCP_ACCESS_TOKEN", "s3cret")
    with TestClient(http_app.build_app()) as c:
        yield c


def test_health_needs_no_token(client):
    r = client.get("/health")
    assert (r.status_code, r.text) == (200, "ok")


@pytest.mark.parametrize("extra", [{}, {"Authorization": "Bearer wrong"}])
def test_mcp_rejects_missing_or_wrong_token(client, extra):
    r = client.post("/mcp", json=INIT, headers=HEADERS | extra)
    assert r.status_code == 401


@pytest.mark.parametrize("how", ["header", "query"])
def test_mcp_lists_tools_with_token(client, how):
    url, headers = "/mcp", dict(HEADERS)
    if how == "header":
        headers["Authorization"] = "Bearer s3cret"
    else:
        url += "?key=s3cret"
    assert client.post(url, json=INIT, headers=headers).status_code == 200
    r = client.post(url, json=LIST, headers=headers | {"MCP-Protocol-Version": "2025-06-18"})
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"current_weather", "forecast", "air_quality", "next_trains", "route", "list_districts"}
