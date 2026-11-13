"""Seoul Commute MCP server.

Exposes the Phase 1 data sources as MCP tools. Any MCP client (Claude Desktop,
Cursor, ...) can call them.

Dev:   uv run mcp dev server.py      (opens MCP Inspector in browser)
Run:   uv run server.py              (stdio, used by Claude Desktop)
"""
import faulthandler
import logging
import os
import sys
from urllib.parse import quote

# When started by briefing/llm.py, write our stderr (tracebacks, crashes) to a
# file: the MCP client otherwise only reports "Connection closed".
if os.environ.get("SERVER_LOG"):
    sys.stderr = open(os.environ["SERVER_LOG"], "a", buffering=1)
    faulthandler.enable(sys.stderr)

import httpx
from mcp.server.mcpserver import MCPServer

from sources import airkorea, kma, route as routes, subway
from sources.districts import DISTRICTS
from sources.http import ApiError, check_name

INSTRUCTIONS = """Live Seoul commute data: weather now, hourly forecast, air quality, subway arrivals, subway routes.
Coverage: Seoul's 25 districts only (not Gyeonggi, e.g. Bundang, Ilsan, Incheon).
Stop counts, journey times, transfers and which way to go come ONLY from the
`route` tool. Never estimate them from memory, not even "about" or "roughly":
memory-based answers have been wrong. If the user's start or end point is
unclear, ask or state your assumption (and which station you used).
Rain or temperature later today come ONLY from the `forecast` tool."""

mcp = MCPServer("seoul-commute", instructions=INSTRUCTIONS)

# httpx logs every request URL at INFO, and our URLs carry the API keys
# (serviceKey=..., the Seoul key in the path). Keep keys out of terminals and logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# Anything a tool call can hit at runtime: bad input, API error, missing key,
# network timeout, unexpected response shape.
ERRORS = (ApiError, ValueError, KeyError, RuntimeError, httpx.HTTPError)


# Fault injection for evals: EVAL_FAIL=air_quality,route makes those tools
# answer like an outage, to test that the model never reassures on missing data.
# Never set in normal use (Claude Desktop, the briefing).
EVAL_FAIL = {t.strip() for t in os.environ.get("EVAL_FAIL", "").split(",") if t.strip()}
OUTAGE = "Error: HTTP 503: Service Unavailable"


# Eval case 28: after a route error the model gave "about 16-17 stops" from
# memory. Say it right next to the error.
ROUTE_DOWN = ("\nNo route data: do not give stop counts, journey times or transfers "
              "from memory. Tell the user the route lookup is unavailable.")


# Key values to scrub from anything we send back or log. Our own error
# messages never contain them, but an upstream reply or a library error might
# (the keys travel in request URLs).
SECRET_ENV = ("DATA_GO_KR_KEY", "SEOUL_API_KEY", "MCP_ACCESS_TOKEN")


def redact(text: str) -> str:
    for name in SECRET_ENV:
        value = os.environ.get(name, "").strip()
        if len(value) >= 8:
            text = text.replace(value, "[redacted]")
            text = text.replace(quote(value, safe=""), "[redacted]")
    return text


def _err(e: Exception) -> str:
    # Return errors as text so the model can recover instead of crashing.
    # Full details go to stderr (Cloud Logging / logs/mcp-server.log), redacted.
    # Network errors get a generic message: httpx errors can carry the request URL.
    print(redact(f"tool error: {type(e).__name__}: {e}"), file=sys.stderr, flush=True)
    if isinstance(e, httpx.HTTPError):
        return f"Error: network problem reaching the data source ({type(e).__name__}). Try again shortly."
    return "Error: " + redact(str(e))


@mcp.tool()
async def current_weather(district: str) -> str:
    """Current weather in a Seoul district: temperature, rain, humidity, wind.

    district: Seoul district (구) in English or Korean, e.g. 'Mapo', 'Gangnam', '마포구'.
    For a trip between two districts, call once for each district.
    """
    if "current_weather" in EVAL_FAIL:
        return OUTAGE
    try:
        w = await kma.current(district)
    except ERRORS as e:
        return _err(e)
    rain = f"{w['precip']}, {w['rain_mm_1h']} mm last hour" if w["precip"] != "none" else "no rain"
    return (f"{w['district']} at {w['observed']} KST: {w['temp_c']}°C, {rain}, "
            f"humidity {w['humidity_pct']}%, wind {w['wind_ms']} m/s.")


@mcp.tool()
async def forecast(district: str, hours: int = 12) -> str:
    """Hourly weather forecast (KMA 단기예보) for a Seoul district: temperature,
    chance of rain and expected rain per hour, for the next 1-24 hours.

    Use for "will it rain later / this evening / on my way home?". For a trip
    between two districts, call once for each district.
    district: e.g. 'Mapo', 'Gangnam', '마포구'. hours: 1-24 (default 12).
    """
    if "forecast" in EVAL_FAIL:
        return OUTAGE
    try:
        fc = await kma.forecast(district, hours)
    except ERRORS as e:
        return _err(e)
    rows = [f"- {h['time']}: {h['temp_c']}°C, rain chance {h['pop']}%"
            + (f", {h['precip']} {h['pcp']}" if h["precip"] != "none" else "")
            for h in fc["hours"]]
    wet = kma.wet_hours(fc)
    head = (f"{fc['district']} forecast (KMA issue {fc['issued']} KST). "
            + (f"Rain likely from {wet[0]['time']}." if wet
               else f"No rain expected until {fc['hours'][-1]['time']}."))
    return head + "\n" + "\n".join(rows)


@mcp.tool()
async def air_quality(district: str) -> str:
    """Current fine dust (PM10) and ultrafine dust (PM2.5) in a Seoul district, with Korean grade.

    district: Seoul district in English or Korean, e.g. 'Mapo', '노원구'.
    Grades: good / moderate / bad / very bad. Suggest a mask at 'bad' or worse.
    For a trip between two districts, call once for each district.
    """
    if "air_quality" in EVAL_FAIL:
        return OUTAGE
    try:
        a = await airkorea.current(district)
    except ERRORS as e:
        return _err(e)
    return (f"{a['station']} at {a['measured']}: PM10 {a['pm10']} µg/m³ ({a['pm10_grade']}), "
            f"PM2.5 {a['pm25']} µg/m³ ({a['pm25_grade']}).")


@mcp.tool()
async def next_trains(station: str, per_direction: int = 2) -> str:
    """Next arriving Seoul subway trains at a station, with direction and ETA.

    station: station name in KOREAN without '역', e.g. '강남', '홍대입구', '서울'.
    Translate English names to Korean before calling (Gangnam -> 강남, Hongik Univ -> 홍대입구).
    per_direction: trains to show for each line and direction (1-3, default 2).
    Every line and direction serving the station is always included.

    Arrivals at ONE station only. For which direction to take, stop counts,
    journey time or transfers, call `route`; never estimate them from memory.
    """
    if "next_trains" in EVAL_FAIL:
        return OUTAGE
    per_direction = max(1, min(per_direction, 3))  # keep responses short
    try:
        station = check_name(station)
        trains = subway.per_direction(await subway.arrivals(station), per_direction)
    except ERRORS as e:
        return _err(e)
    if not trains:
        return f"No arrival data for {station!r}. Check the Korean station name."
    lines = [f"- [{t['line']}] {t['direction']}: {t['message']}" for t in trains]
    # Repeated in the result because some MCP clients don't show the model the
    # server instructions, and a rule next to the data is hardest to miss.
    return (f"Next trains at {station}:\n" + "\n".join(lines)
            + "\n(Arrivals only. For direction, stops, journey time or transfers use the "
              "`route` tool; never estimate them from memory.)")


@mcp.tool()
async def route(from_station: str, to_station: str, prefer: str = "fastest") -> str:
    """Subway route between two stations from Seoul Metro's timetable: each line
    to ride, which direction (toward = the next station, matching the 방면 sign
    in next_trains), stop counts, transfers with walking time, departure and
    arrival times, total minutes and card fare.

    from_station / to_station: station names in KOREAN without '역', e.g. '홍대입구',
    '강남'. Translate English names first (Hongik Univ -> 홍대입구, Gangnam -> 강남).
    If the user gives a district or neighbourhood, pick its main station and say so.
    prefer: 'fastest' (default), 'fewest_transfers' or 'shortest'.
    Times assume the next train from now; pair with next_trains for live arrivals.

    Always call this for stop counts, journey times, transfers or fares, even if
    the user says an estimate from memory is fine: memory answers have been wrong.
    For a commute check, also call next_trains at the boarding station and
    current_weather and air_quality for BOTH the start and end districts.
    """
    if "route" in EVAL_FAIL:
        return OUTAGE + ROUTE_DOWN
    try:
        body = await routes.find(from_station, to_station, prefer)
    except ERRORS as e:
        return _err(e) + ROUTE_DOWN
    return routes.describe(body)


@mcp.tool()
def list_districts() -> str:
    """List the 25 Seoul districts this server supports (English and Korean names)."""
    return ", ".join(f"{en} ({ko})" for ko, (en, _, _) in DISTRICTS.items())


if __name__ == "__main__":
    mcp.run(transport="stdio")
