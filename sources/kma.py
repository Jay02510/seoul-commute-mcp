"""KMA weather via data.go.kr (VilageFcstInfoService_2.0, one 활용신청 covers both):

- 초단기실황 `getUltraSrtNcst`: current observed weather (`current`)
- 단기예보 `getVilageFcst`: hourly forecast for the next ~2 days (`forecast`),
  used to warn about rain later in the day.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import get_key
from .districts import grid, resolve
from .http import ApiError, get_json

URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
FCST_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KST = ZoneInfo("Asia/Seoul")

PTY = {"0": "none", "1": "rain", "2": "rain/snow", "3": "snow", "5": "drizzle", "6": "drizzle/snow", "7": "snow flurries"}


def latest_base(now: datetime | None = None) -> tuple[str, str]:
    """Observations publish hourly and appear ~40 min later. Before :45, use the previous hour."""
    now = now or datetime.now(KST)
    if now.minute < 45:
        now -= timedelta(hours=1)
    return now.strftime("%Y%m%d"), now.strftime("%H00")


async def current(district: str) -> dict:
    nx, ny = grid(district)
    base_date, base_time = latest_base()
    data = await get_json(URL, {
        "serviceKey": get_key("DATA_GO_KR_KEY"),  # decoded key; httpx encodes it
        "dataType": "JSON",
        "numOfRows": 20,
        "pageNo": 1,
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    })
    header = data["response"]["header"]
    if header["resultCode"] != "00":
        raise ApiError(f"KMA {header['resultCode']}: {header['resultMsg']}")
    items = data["response"]["body"]["items"]["item"]
    obs = {i["category"]: i["obsrValue"] for i in items}
    return {
        "district": resolve(district),
        "observed": f"{base_date} {base_time}",
        "temp_c": float(obs["T1H"]),
        "rain_mm_1h": float(obs.get("RN1", 0)),
        "precip": PTY.get(obs.get("PTY", "0"), "unknown"),
        "humidity_pct": int(float(obs["REH"])),
        "wind_ms": float(obs["WSD"]),
    }


# 단기예보: forecast PTY codes differ from the observation codes above.
FCST_PTY = {"0": "none", "1": "rain", "2": "rain/snow", "3": "snow", "4": "shower"}
FCST_BASES = (2, 5, 8, 11, 14, 17, 20, 23)   # issued 8 times a day, online ~10 min later


def forecast_base(now: datetime | None = None) -> tuple[str, str]:
    """Latest 단기예보 issue that is online: base hour + 15 minutes margin.
    Before 02:15 that is 23:00 the day before."""
    now = (now or datetime.now(KST)) - timedelta(minutes=15)
    past = [h for h in FCST_BASES if h <= now.hour]
    if not past:
        now -= timedelta(days=1)
        past = [23]
    return now.strftime("%Y%m%d"), f"{past[-1]:02d}00"


async def forecast(district: str, hours: int = 12, now: datetime | None = None) -> dict:
    """Hourly forecast for the next `hours` hours (1-24):
    {"district", "issued", "hours": [{"time": "HH:00", "date": "YYYYMMDD",
    "temp_c", "pop", "precip", "pcp"}]}. `pop` is the chance of rain in %,
    `pcp` KMA's 1-hour amount text ('강수없음', '1mm 미만', '2.0mm')."""
    hours = max(1, min(int(hours), 24))
    now = (now or datetime.now(KST)).astimezone(KST)
    nx, ny = grid(district)
    base_date, base_time = forecast_base(now)
    data = await get_json(FCST_URL, {
        "serviceKey": get_key("DATA_GO_KR_KEY"),
        "dataType": "JSON",
        "numOfRows": 1000,     # ~12 categories per hour; one call covers ~3 days
        "pageNo": 1,
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    })
    header = data["response"]["header"]
    if header["resultCode"] != "00":
        raise ApiError(f"KMA forecast {header['resultCode']}: {header['resultMsg']}")
    by_hour: dict[str, dict] = {}
    for i in data["response"]["body"]["items"]["item"]:
        by_hour.setdefault(i["fcstDate"] + i["fcstTime"], {})[i["category"]] = i["fcstValue"]
    start = now.strftime("%Y%m%d%H00")
    out = []
    for key in sorted(k for k in by_hour if k >= start)[:hours]:
        v = by_hour[key]
        out.append({
            "date": key[:8],
            "time": f"{key[8:10]}:00",
            "temp_c": float(v["TMP"]) if "TMP" in v else None,
            "pop": int(v.get("POP", 0)),
            "precip": FCST_PTY.get(v.get("PTY", "0"), "unknown"),
            "pcp": v.get("PCP", "강수없음"),
        })
    if not out:
        raise ApiError(f"KMA forecast: no hours after {start} in issue {base_date} {base_time}")
    return {"district": resolve(district), "issued": f"{base_date} {base_time}", "hours": out}


RAIN_POP = 60   # % chance from which we call it "rain likely" (KMA's own wording starts at 60)


def wet_hours(fc: dict, pop_min: int = RAIN_POP) -> list[dict]:
    """Forecast hours with rain or snow expected, or a chance of at least pop_min %."""
    return [h for h in fc["hours"] if h["precip"] != "none" or h["pop"] >= pop_min]

