"""Seoul realtime subway arrivals via data.seoul.go.kr.

Limit: 1,000 calls/day per key, so replies are cached per station for
SUBWAY_CACHE_SECONDS (default 30; 0 turns the cache off).
Station names: Korean, without '역' (e.g. '강남', '서울'). Some need suffixes,
e.g. '천호(풍납토성)'.
"""
import os
import time
from urllib.parse import quote

from .config import get_key
from .http import ApiError, check_name, get_json

# subwayId -> line name (Seoul Open Data codes)
LINES = {
    "1001": "Line 1", "1002": "Line 2", "1003": "Line 3", "1004": "Line 4",
    "1005": "Line 5", "1006": "Line 6", "1007": "Line 7", "1008": "Line 8",
    "1009": "Line 9", "1032": "GTX-A", "1061": "Jungang", "1063": "Gyeongui-Jungang",
    "1065": "Airport Railroad", "1067": "Gyeongchun", "1075": "Suin-Bundang",
    "1077": "Shinbundang", "1081": "Gyeonggang", "1092": "Ui-Sinseol", "1093": "Seohae",
}

BASE = "http://swopenapi.seoul.go.kr/api/subway/{key}/json/realtimeStationArrival/0/{n}/{station}"


# One API call costs the same quota whatever the row count, so always ask for
# plenty. With a small n, busy transfer stations (공덕: 4 lines) lose whole
# directions: the 10-row cut dropped Line 5 toward 애오개 and Line 6 toward 효창.
FETCH_ROWS = 40


def per_direction(trains: list[dict], k: int = 2) -> list[dict]:
    """Keep the next k trains for each (line, direction sign), grouped by line.
    The direction sign is the part after ' - ' in trainLineNm, e.g. '합정방면'."""
    seen: dict[tuple, int] = {}
    out = []
    for t in trains:
        key = (t["line"], t["updown"], (t["direction"] or "").split(" - ")[-1].replace(" (급행)", ""))
        if seen.get(key, 0) < k:
            seen[key] = seen.get(key, 0) + 1
            out.append(t)
    order = {}
    for t in out:
        order.setdefault(t["line"], len(order))
    return sorted(out, key=lambda t: order[t["line"]])  # stable: keeps arrival order inside a line


# station -> (monotonic time fetched, rows). In memory only: one cache per
# server process, empty again after a restart.
_cache: dict[str, tuple[float, list[dict]]] = {}
_now = time.monotonic  # replaced in tests


def cache_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("SUBWAY_CACHE_SECONDS", "30")))
    except ValueError:
        return 30.0


def clear_cache() -> None:
    _cache.clear()


async def arrivals(station: str, n: int = FETCH_ROWS) -> list[dict]:
    """Next trains at a station. Served from the cache when a reply for the same
    station is younger than cache_seconds(); `seconds` is then reduced by the
    reply's age so countdowns stay roughly right. Errors are never cached."""
    station = check_name(station)
    ttl = cache_seconds()
    hit = _cache.get(station)
    if ttl and hit and _now() - hit[0] < ttl:
        age = int(_now() - hit[0])
        return [dict(t, seconds=max(0, t["seconds"] - age)) for t in hit[1]]
    rows = await _fetch(station, n)
    if ttl:
        _cache[station] = (_now(), rows)
    return [dict(t) for t in rows]


async def _fetch(station: str, n: int) -> list[dict]:
    url = BASE.format(key=get_key("SEOUL_API_KEY"), n=n, station=quote(station, safe=""))
    data = await get_json(url)
    err = data.get("errorMessage") or {}
    if err.get("code") == "INFO-200":  # no data: unknown station or no trains running
        return []
    if err.get("code") not in (None, "INFO-000"):
        raise ApiError(f"Seoul subway {err.get('code')}: {err.get('message')}")
    return [
        {
            "line_id": row.get("subwayId"),
            "line": LINES.get(str(row.get("subwayId")), f"line {row.get('subwayId')}"),
            "direction": row.get("trainLineNm"),  # e.g. '성수행 - 역삼방면'
            "updown": row.get("updnLine"),
            "message": row.get("arvlMsg2"),       # e.g. '전역 도착', '3분 후'
            "seconds": int(row.get("barvlDt") or 0),
        }
        for row in data.get("realtimeArrivalList", [])
    ]
