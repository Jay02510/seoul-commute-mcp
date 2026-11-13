"""sources/http.py: data.go.kr answers auth errors with XML even when asked for JSON."""
import asyncio

import httpx
import pytest

from sources import http


def use_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def client(*a, **kw):
        return real(*a, transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(http.httpx, "AsyncClient", client)


def test_json_ok(monkeypatch):
    use_transport(monkeypatch, lambda req: httpx.Response(200, json={"ok": 1}))
    assert asyncio.run(http.get_json("https://example.test/x")) == {"ok": 1}


def test_xml_auth_error(monkeypatch):
    xml = "<OpenAPI_ServiceResponse><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></OpenAPI_ServiceResponse>"
    use_transport(monkeypatch, lambda req: httpx.Response(200, text=xml))
    with pytest.raises(http.ApiError, match="XML instead of JSON"):
        asyncio.run(http.get_json("https://example.test/x"))


def test_http_status_error(monkeypatch):
    use_transport(monkeypatch, lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(http.ApiError, match="HTTP 500"):
        asyncio.run(http.get_json("https://example.test/x"))


def test_offline_guard_blocks_real_requests():
    """conftest.py must stop any real API call (and any use of real keys)."""
    with pytest.raises(AssertionError, match="real HTTP request"):
        asyncio.run(http.get_json("https://apis.data.go.kr/x"))
