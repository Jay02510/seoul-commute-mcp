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


def test_connect_timeout_is_retried(monkeypatch):
    monkeypatch.setattr(http, "RETRY_DELAYS", (0, 0))
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectTimeout("timed out", request=req)
        return httpx.Response(200, json={"ok": 1})

    use_transport(monkeypatch, handler)
    assert asyncio.run(http.get_json("https://example.test/x")) == {"ok": 1}
    assert len(calls) == 3


def test_connect_timeout_gives_up(monkeypatch):
    monkeypatch.setattr(http, "RETRY_DELAYS", (0, 0))
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ConnectTimeout("timed out", request=req)

    use_transport(monkeypatch, handler)
    with pytest.raises(httpx.ConnectTimeout):
        asyncio.run(http.get_json("https://example.test/x"))
    assert len(calls) == 3


def test_error_reply_is_not_retried(monkeypatch):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500, text="boom")

    use_transport(monkeypatch, handler)
    with pytest.raises(http.ApiError):
        asyncio.run(http.get_json("https://example.test/x"))
    assert len(calls) == 1


def test_retry_log_hides_the_key(monkeypatch, capsys):
    monkeypatch.setattr(http, "RETRY_DELAYS", (0,))
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=req)
        return httpx.Response(200, json={"ok": 1})

    use_transport(monkeypatch, handler)
    asyncio.run(http.get_json("https://apis.example.test/x?serviceKey=SECRET"))
    err = capsys.readouterr().err
    assert "apis.example.test" in err and "SECRET" not in err
