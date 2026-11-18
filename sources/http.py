"""Shared HTTP helper. data.go.kr returns XML on auth errors even when you ask for JSON."""
import asyncio
import sys
from urllib.parse import urlsplit

import httpx

# Connecting gets its own short limit; reading the reply keeps 10 s.
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# From Cloud Run, connections to apis.data.go.kr sometimes time out for a while
# and then work again (2026-11-17/18). Retry connection failures only: a reply
# that arrived, even an error, is never re-sent.
RETRY_DELAYS = (1.0, 3.0)


class ApiError(Exception):
    pass


async def _get(url: str, params: dict | None) -> httpx.Response:
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                return await client.get(url, params=params)
        except (httpx.ConnectTimeout, httpx.ConnectError) as e:
            if attempt == len(RETRY_DELAYS):
                raise
            # Host only: the query string holds the API key.
            print(f"retry {attempt + 1}/{len(RETRY_DELAYS)} {urlsplit(url).hostname}: "
                  f"{type(e).__name__}", file=sys.stderr)
            await asyncio.sleep(RETRY_DELAYS[attempt])


async def get_json(url: str, params: dict | None = None) -> dict:
    r = await _get(url, params)
    text = r.text.strip()
    if r.status_code != 200:
        raise ApiError(f"HTTP {r.status_code}: {text[:200]}")
    if text.startswith("<"):
        # e.g. <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
        raise ApiError(f"Got XML instead of JSON (usually a key problem): {text[:300]}")
    return r.json()


MAX_NAME = 30  # longest real station name is ~15 characters


def check_name(name: str) -> str:
    """Clean a station name from a tool call: trim, drop a trailing '역', and
    reject empty or overlong input. The name goes into the Seoul API's URL path,
    so it is also percent-encoded with safe="" by the caller (no '/' escapes)."""
    from .stations import to_korean  # English names ('Gangnam') -> '강남'
    name = (name or "").strip()
    if len(name) > 2 * MAX_NAME:          # English names run longer than Korean ones
        raise ValueError(f"station name too long (max {MAX_NAME} characters)")
    name = to_korean(name).removesuffix("역") if name else name
    if not name:
        raise ValueError("station name is empty")
    if len(name) > MAX_NAME:
        raise ValueError(f"station name too long (max {MAX_NAME} characters)")
    return name
