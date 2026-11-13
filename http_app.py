"""Remote MCP: the same tools as server.py, served over Streamable HTTP.

Local stdio use (Claude Desktop, the briefing) is unchanged; this file is only
for the hosted version (Cloud Run, BUILD_GUIDE Step 13).

    PORT=8080 MCP_ACCESS_TOKEN=secret uv run python http_app.py

Endpoints:
  /mcp      the MCP endpoint. Needs the token when MCP_ACCESS_TOKEN is set,
            either as "Authorization: Bearer <token>" or as ?key=<token>
            (for clients that only take a URL).
  /health   plain "ok", no token, for uptime checks.

Stateless with JSON replies: every request stands alone, so any Cloud Run
instance can answer it and no session needs to stick to one instance.
"""
import hmac
import os
from urllib.parse import parse_qs

from starlette.responses import PlainTextResponse

from server import mcp


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return PlainTextResponse("ok")


class TokenGate:
    """ASGI middleware: reject /mcp requests without the access token.
    Without a token the public URL would let anyone spend the API quotas."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode()

    def _ok(self, scope) -> bool:
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"")
        if auth.lower().startswith(b"bearer ") and hmac.compare_digest(auth[7:].strip(), self.token):
            return True
        key = parse_qs(scope.get("query_string", b"").decode()).get("key", [""])[0]
        return hmac.compare_digest(key.encode(), self.token)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/mcp") and not self._ok(scope):
            await PlainTextResponse("missing or wrong access token", status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def build_app():
    app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",  # no localhost-only DNS-rebinding filter: Cloud Run's Host header is its own URL
    )
    token = os.environ.get("MCP_ACCESS_TOKEN", "").strip()
    return TokenGate(app, token) if token else app


if __name__ == "__main__":
    import uvicorn

    if not os.environ.get("MCP_ACCESS_TOKEN", "").strip():
        print("warning: MCP_ACCESS_TOKEN not set, /mcp is open to anyone", flush=True)
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=True, forwarded_allow_ips="*")
