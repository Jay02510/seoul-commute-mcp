"""Fetch live data for a route and turn it into a short briefing.

Rule-based for now (no LLM). `gather()` returns plain data and `compose()` turns
it into text, so an LLM writer can replace `compose()` later without touching
data fetching.
"""
import asyncio
import sys
from datetime import datetime

from sources import airkorea, kma, route as routes, subway
from sources.districts import DISTRICTS

from .store import dest as dest_of

FORECAST_HOURS = 15   # 07:45 run covers up to 21:00, the trip home included
GRADE_RANK = {"good": 0, "moderate": 1, "bad": 2, "very bad": 3}


async def gather(route) -> dict:
    """Call every source in parallel. A failed source becomes an Exception value
    instead of killing the whole briefing."""
    jobs = {
        "weather_home": kma.current(route["home"]),
        "weather_work": kma.current(route["work"]),
        "air_home": airkorea.current(route["home"]),
        "air_work": airkorea.current(route["work"]),
        "trains": subway.arrivals(route["station"]),
        "forecast_home": kma.forecast(route["home"], FORECAST_HOURS),
        "forecast_work": kma.forecast(route["work"], FORECAST_HOURS),
    }
    if dest_of(route):  # journey line only for routes with a destination station
        jobs["journey"] = routes.commute(route["station"], dest_of(route), route["toward"])
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    data = dict(zip(jobs, results))
    for k, v in data.items():
        if isinstance(v, Exception):  # full reason to stderr (logs/briefing.log under launchd)
            print(f"{datetime.now():%F %T} {route['name']}: {k} failed: {type(v).__name__}: {v}",
                  file=sys.stderr)
    return data


def _short(district: str) -> str:
    """'마포구' -> 'Mapo'. Falls back to the input for unknown names."""
    return DISTRICTS[district][0] if district in DISTRICTS else district


def weather_advice(w: dict) -> list[str]:
    tips = []
    if w["precip"] != "none":
        tips.append(f"☔ {w['precip'].capitalize()} now ({w['rain_mm_1h']} mm last hour). Take an umbrella.")
    t = w["temp_c"]
    if t < 0:
        tips.append("🥶 Below freezing: heavy coat, gloves.")
    elif t < 5:
        tips.append("🧥 Cold: warm coat.")
    elif t < 12:
        tips.append("🧥 Cool: bring a jacket.")
    elif t >= 28:
        tips.append("🥵 Hot: carry water.")
    if w["wind_ms"] >= 9:
        tips.append(f"💨 Strong wind ({w['wind_ms']} m/s).")
    return tips


def air_advice(airs: list[dict]) -> str | None:
    worst = max(airs, key=lambda a: max(GRADE_RANK.get(a["pm10_grade"], 0),
                                        GRADE_RANK.get(a["pm25_grade"], 0)))
    level = max(GRADE_RANK.get(worst["pm10_grade"], 0), GRADE_RANK.get(worst["pm25_grade"], 0))
    if level >= 2:
        return f"😷 Wear a mask: {_short(worst['station'])} PM2.5 {worst['pm25']} ({worst['pm25_grade']}), PM10 {worst['pm10']} ({worst['pm10_grade']})."
    return None


def _why(e: Exception) -> str:
    """Short reason for the phone. Full errors (e.g. 300 chars of XML) go to
    stderr / the log, not the message. Some httpx errors have an empty str()."""
    text = str(e).splitlines()[0] if str(e) else type(e).__name__
    return text if len(text) <= 60 else text[:57] + "..."


def _ok(x) -> bool:
    return not isinstance(x, Exception)


def compose(route, data: dict, now: datetime | None = None) -> str:
    """Rules writer. Every part of the route (weather and air at each end, the
    trains) is either shown or marked unavailable: never silently left out."""
    now = now or datetime.now()
    home, work = _short(route["home"]), _short(route["work"])
    lines = [f"🚇 {route['name']}: {home} → {work} · {now:%a %H:%M}", ""]
    tips: list[str] = []
    missing: list[str] = []      # everything that failed, listed in the footer

    # Weather: one entry per end, failed ends labelled
    ends = [(home, data["weather_home"]), (work, data["weather_work"])]
    weathers = [(name, w) for name, w in ends if _ok(w)]
    for name, w in ends:
        if not _ok(w):
            missing.append(f"{name} weather")
    if not weathers:
        lines.append(f"Weather: unavailable ({_why(data['weather_home'])})")
    else:
        parts = [f"{name} {w['temp_c']}°C" if _ok(w) else f"{name} unavailable"
                 for name, w in ends]
        wet = [(name, w) for name, w in weathers if w["precip"] != "none"]
        if wet:
            parts.append(", ".join(f"{w['precip']} now in {name}" for name, w in wet))
        else:
            parts.append("dry" if len(weathers) == 2 else f"dry in {weathers[0][0]}")
        lines.append("Weather: " + ", ".join(parts))
        # Advice from the worst checked end: wettest, coldest, windiest
        if wet:
            name, w = wet[0]
            where = "" if len(wet) == 2 else f" in {name}"
            tips.append(f"☔ {w['precip'].capitalize()} now{where} ({w['rain_mm_1h']} mm last hour). Take an umbrella.")
        coldest = min((w for _, w in weathers), key=lambda w: w["temp_c"])
        windiest = max((w for _, w in weathers), key=lambda w: w["wind_ms"])
        tips += weather_advice({**coldest, "precip": "none", "wind_ms": windiest["wind_ms"]})

    # Later today (단기예보). Only if gather() asked for it, so older callers
    # and tests without forecast keys still work. The umbrella tip for rain
    # NOW comes from the weather block above; this one is for rain later.
    if "forecast_home" in data:
        fends = [(home, data["forecast_home"]), (work, data["forecast_work"])]
        fcs = [(name, f) for name, f in fends if _ok(f)]
        for name, f in fends:
            if not _ok(f):
                missing.append(f"{name} forecast")
        if not fcs:
            lines.append(f"Later: forecast unavailable ({_why(data['forecast_home'])})")
        else:
            firsts = [(name, kma.wet_hours(f)[0]) for name, f in fcs if kma.wet_hours(f)]
            if firsts:
                desc = ", ".join(f"{h['precip'] if h['precip'] != 'none' else 'rain'} likely from "
                                 f"{h['time']} in {name} ({h['pop']}%)" for name, h in firsts)
                lines.append(f"Later: {desc}")
                wet_now = any(w["precip"] != "none" for _, w in weathers)
                if not wet_now:
                    tips.append(f"☂️ Take an umbrella for later ({firsts[0][1]['time']}).")
            else:
                until = min(f["hours"][-1]["time"] for _, f in fcs)
                where = "" if len(fcs) == 2 else f" in {fcs[0][0]}"
                lines.append(f"Later: no rain expected{where} until {until}")

    # Air: same idea
    ends = [(home, data["air_home"]), (work, data["air_work"])]
    airs = [a for _, a in ends if _ok(a)]
    for name, a in ends:
        if not _ok(a):
            missing.append(f"{name} air")
    if not airs:
        lines.append(f"Air: unavailable ({_why(data['air_home'])})")
    else:
        lines.append("Air: " + ", ".join(
            f"{name} PM2.5 {a['pm25']} ({a['pm25_grade']})" if _ok(a) else f"{name} unavailable"
            for name, a in ends))
        mask = air_advice(airs)
        if mask:
            tips.append(mask)
        # An unknown grade is missing data: never let it count as "good" and
        # produce "No mask needed".
        for name, a in ends:
            if _ok(a) and "n/a" in (a["pm10_grade"], a["pm25_grade"]):
                missing.append(f"{name} air grade")

    # Trains
    trains = data["trains"]
    lines.append("")
    if not _ok(trains):
        lines.append(f"Trains at {route['station']}: unavailable ({_why(trains)})")
    else:
        toward = route["toward"]
        picked = [t for t in trains if toward in (t["direction"] or "")] if toward else trains
        label = f"{route['station']} toward {toward}" if toward else route["station"]
        if picked:
            lines.append(f"Next trains, {label}:")
            lines += [f"• [{t['line']}] {t['message']}" for t in picked[:3]]
        else:
            lines.append(f"No live trains {('toward ' + toward) if toward else ''} at {route['station']} right now.".replace("  ", " "))

    # Journey (only if the route has a destination station). Numbers come from
    # the Seoul Metro timetable API, never estimated.
    if "journey" in data:
        j, to = data["journey"], dest_of(route)
        if not _ok(j):
            lines.append(f"Journey to {to}: unavailable ({_why(j)})")
            missing.append("journey")
        else:
            lines.append(f"Journey to {to}: {routes.summary(j)}")
            api_toward = routes.first_toward(j)
            if route["toward"] and api_toward and api_toward != route["toward"]:
                tips.append(f"⚠️ Suggested route boards toward {api_toward}, not {route['toward']} "
                            f"(saved direction). Check before you go.")

    # Footer. Never reassure ("no umbrella or mask needed") unless both ends
    # of both weather and air were checked. A missing journey doesn't block it.
    footer = list(tips)
    wx_air_missing = [m for m in missing if m != "journey"]
    if not tips and not wx_air_missing:
        footer.append("✅ No umbrella or mask needed.")
    if missing:
        footer.append(f"⚠️ No data for {', '.join(missing)}: check it yourself.")
    lines += [""] + footer
    return "\n".join(lines)
