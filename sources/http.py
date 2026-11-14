"""Shared HTTP helper. data.go.kr returns XML on auth errors even when you ask for JSON."""
import httpx

TIMEOUT = 10.0


class ApiError(Exception):
    pass


async def get_json(url: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(url, params=params)
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
