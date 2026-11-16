"""Subway routes via Seoul Metro's shortest-path API (data.go.kr 15143842).

Give a departure and arrival station; get the timetable-based route with
every leg, transfer, stop count, time and fare. Same DATA_GO_KR_KEY as
KMA/AirKorea, separate 활용신청. Dev account: 10,000 calls/day.

Station names: Korean, without '역' (e.g. '홍대입구', '강남'), the same names
the realtime arrivals API uses.
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import get_key
from .http import ApiError, check_name, get_json

URL = "https://apis.data.go.kr/B553766/path2/getShtrmPath2"
KST = ZoneInfo("Asia/Seoul")

SEARCH_TYPES = {"fastest": "duration", "fewest_transfers": "transfer", "shortest": "distance"}

ERRORS = {
    "01": "departure or arrival station missing",
    "10": "unknown station name (use the Korean name without '역', e.g. '홍대입구')",
    "11": "bad search time format",
    "99": "route server error",
}


async def _call(src: str, dst: str, prefer: str, when: datetime) -> dict:
    """One API call; returns the body (may have no paths if a name didn't match)."""
    data = await get_json(URL, params={
        "serviceKey": get_key("DATA_GO_KR_KEY"),
        "dataType": "JSON",
        "dptreStn": src,
        "arvlStn": dst,
        "searchDt": when.strftime("%Y-%m-%d %H:%M:%S"),
        "searchType": SEARCH_TYPES.get(prefer, "duration"),
    })
    header = data.get("header") or {}
    code = str(header.get("resultCode", "")).zfill(2)
    if code not in ("00", "200"):
        reason = ERRORS.get(code, header.get("resultMsg") or "unknown error")
        raise ApiError(f"Route {src} -> {dst}: {reason} (code {code})")
    if not data.get("body"):
        raise ApiError(f"Route {src} -> {dst}: empty reply")
    return data["body"]


async def find(src: str, dst: str, prefer: str = "fastest", when: datetime | None = None) -> dict:
    """Raw API body for the best route from src to dst.

    Names are tried without '역' first (the usual form, e.g. '강남'). A few
    stations keep '역' in their official name ('서울역'); for those the API
    answers 00 with no paths, so we retry with '역' added back on each side.
    """
    src, dst = (check_name(s) for s in (src, dst))
    when = (when or datetime.now(KST)).astimezone(KST)
    tries = [(src, dst), (src + "역", dst), (src, dst + "역"), (src + "역", dst + "역")]
    for a, b in tries:
        body = await _call(a, b, prefer, when)
        if body.get("paths"):
            return body
    raise ApiError(f"Route {src} -> {dst}: no route found; one of the station names "
                   "did not match (use the Korean name, e.g. '홍대입구', '서울역')")


# A commute route with fewer changes wins unless the fastest one saves more
# than this many minutes (2026-11-13: the API's "fastest" offered 경의선 + 4호선 +
# 2호선 with 2 transfers to save 2 min over riding 2호선 straight through).
COMMUTE_SLACK_MIN = 5


def pick_commute(bodies: list[dict], toward: str = "", slack_min: int = COMMUTE_SLACK_MIN) -> dict:
    """Choose the route a commuter would actually take from several API replies
    (e.g. one per search type). Every route within `slack_min` minutes of the
    fastest qualifies; among those, prefer the saved boarding direction, then
    fewer transfers, then less time."""
    bodies = [b for b in bodies if b and b.get("paths")]
    if not bodies:
        raise ApiError("no route found")
    secs = lambda b: b.get("totalReqHr") or 0
    fastest = min(secs(b) for b in bodies)
    ok = [b for b in bodies if secs(b) <= fastest + slack_min * 60]
    return min(ok, key=lambda b: (bool(toward) and first_toward(b) != toward,
                                  b.get("trsitNmtm") or 0, secs(b)))


async def commute(src: str, dst: str, toward: str = "", when: datetime | None = None) -> dict:
    """Route for a daily commute: asks for both the fastest and the
    fewest-transfers route (two calls, in parallel) and picks with
    `pick_commute`. If only one search works, that one is used."""
    results = await asyncio.gather(find(src, dst, "fastest", when),
                                   find(src, dst, "fewest_transfers", when),
                                   return_exceptions=True)
    bodies = [r for r in results if not isinstance(r, Exception)]
    if not bodies:
        raise results[0]
    return pick_commute(bodies, toward)


def legs(body: dict) -> list[dict]:
    """Collapse station-to-station hops into rides and transfers.

    ride:     {"kind": "ride", "line", "from", "to", "toward", "terminus",
               "stops", "depart", "arrive", "seconds"}
    transfer: {"kind": "transfer", "at", "from_line", "to_line",
               "walk_s", "wait_s"}
    """
    out: list[dict] = []
    for hop in body.get("paths", []):
        a, b = hop["dptreStn"], hop["arvlStn"]
        if hop.get("trsitYn") == "Y":
            out.append({"kind": "transfer", "at": a["stnNm"], "from_line": a["lineNm"],
                        "to_line": b["lineNm"], "walk_s": hop.get("reqHr") or 0,
                        "wait_s": hop.get("wtngHr") or 0})
            continue
        last = out[-1] if out else None
        if last and last["kind"] == "ride" and last["line"] == a["lineNm"]:
            last.update(to=b["stnNm"], stops=last["stops"] + 1,
                        arrive=hop.get("trainArvlTm") or last["arrive"],
                        seconds=last["seconds"] + (hop.get("reqHr") or 0))
        else:
            out.append({"kind": "ride", "line": a["lineNm"], "from": a["stnNm"],
                        "to": b["stnNm"], "toward": b["stnNm"],  # first station after boarding
                        "terminus": hop.get("tmnlStnNm"), "stops": 1,
                        "depart": hop.get("trainDptreTm"), "arrive": hop.get("trainArvlTm"),
                        "seconds": hop.get("reqHr") or 0})
    return out


def _hm(t: str | None) -> str:
    return t[:5] if t else "?"


def _ride_min(p: dict) -> int:
    """Minutes on one train. Given in the tool result so the model never works
    them out itself (eval #24: it subtracted timetable times, and the grounding
    check rightly flagged a number no tool had returned)."""
    if p.get("depart") and p.get("arrive"):
        a, b = (int(t[:2]) * 60 + int(t[3:5]) for t in (p["depart"], p["arrive"]))
        return (b - a) % (24 * 60)
    return round((p.get("seconds") or 0) / 60)


def describe(body: dict) -> str:
    """Plain-text route for the model or a briefing."""
    parts = legs(body)
    rides = [p for p in parts if p["kind"] == "ride"]
    if not rides:
        return "No route found."
    first, last = rides[0], rides[-1]
    stops = sum(r["stops"] for r in rides)
    minutes = round((body.get("totalReqHr") or 0) / 60)
    n_tr = body.get("trsitNmtm") or 0
    head = (f"{first['from']} -> {last['to']}: {minutes} min, {stops} stops, "
            f"{n_tr} transfer{'s' if n_tr != 1 else ''}"
            + (f", card fare {body['totalCardCrg']:,} won" if body.get("totalCardCrg") else "")
            + f". Departs {_hm(first['depart'])}, arrives {_hm(last['arrive'])} (timetable).")
    lines = [head]
    for p in parts:
        if p["kind"] == "ride":
            to = f", train to {p['terminus']}" if p["terminus"] else ""
            lines.append(f"- {p['line']} from {p['from']} toward {p['toward']}{to}: "
                         f"{p['stops']} stop{'s' if p['stops'] != 1 else ''} to {p['to']}, "
                         f"{_ride_min(p)} min ({_hm(p['depart'])}-{_hm(p['arrive'])})")
        else:
            lines.append(f"- Transfer at {p['at']} ({p['from_line']} to {p['to_line']}): "
                         f"about {max(1, round(p['walk_s'] / 60))} min walk"
                         + (f", then about {round(p['wait_s'] / 60)} min wait" if p["wait_s"] >= 60 else ""))
    return "\n".join(lines)


def summary(body: dict) -> str:
    """One line for the briefing, e.g.
    '38 min, 17 stops, no transfers (2호선 toward 합정; timetable 11:26-12:04)'."""
    parts = legs(body)
    rides = [p for p in parts if p["kind"] == "ride"]
    if not rides:
        return "no route found"
    minutes = round((body.get("totalReqHr") or 0) / 60)
    stops = sum(r["stops"] for r in rides)
    transfers = [p for p in parts if p["kind"] == "transfer"]
    if transfers:
        via = "change at " + ", ".join(f"{t['at']} ({t['from_line']} to {t['to_line']})" for t in transfers)
    else:
        via = "no transfers"
    first, last = rides[0], rides[-1]
    return (f"{minutes} min, {stops} stops, {via} "
            f"({first['line']} toward {first['toward']}; timetable {_hm(first['depart'])}-{_hm(last['arrive'])})")


def first_toward(body: dict) -> str | None:
    """Direction of the first ride (the station after boarding), to compare with
    the direction saved for a briefing route."""
    rides = [p for p in legs(body) if p["kind"] == "ride"]
    return rides[0]["toward"] if rides else None
