"""AirKorea realtime air quality per station via data.go.kr.

Seoul's city stations are named after districts (e.g. '마포구'), so we use
the district name as station name. Later: use 측정소정보 getNearbyMsrstnList
to find the closest station to any address.
"""
from .config import get_key
from .districts import resolve
from .http import ApiError, get_json

URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
GRADE = {"1": "good", "2": "moderate", "3": "bad", "4": "very bad"}

# Korean Ministry of Environment bands (µg/m³), upper bound of each grade.
# AirKorea's own pm10Grade/pm25Grade fields follow a 24-hour average and are
# often empty for a few hours, so a current reading of 39 could show as
# "moderate" or "n/a". We grade the hourly value ourselves and fall back to the
# API's grade only when there is no number (e.g. '-' when a sensor is down).
BANDS = {
    "pm10": [(30, "good"), (80, "moderate"), (150, "bad")],
    "pm25": [(15, "good"), (35, "moderate"), (75, "bad")],
}


def grade(kind: str, value, api_grade=None) -> str:
    """'good' / 'moderate' / 'bad' / 'very bad' for a reading, or 'n/a'."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return GRADE.get(str(api_grade or ""), "n/a")
    for top, name in BANDS[kind]:
        if v <= top:
            return name
    return "very bad"


async def current(district: str) -> dict:
    station = resolve(district)
    data = await get_json(URL, {
        "serviceKey": get_key("DATA_GO_KR_KEY"),
        "returnType": "json",
        "numOfRows": 1,
        "pageNo": 1,
        "stationName": station,
        "dataTerm": "DAILY",
        "ver": "1.0",
    })
    header = data["response"]["header"]
    if header["resultCode"] != "00":
        raise ApiError(f"AirKorea {header['resultCode']}: {header['resultMsg']}")
    items = data["response"]["body"]["items"]
    if not items:
        raise ApiError(f"No air data for station {station!r}")
    row = items[0]
    return {
        "station": station,
        "measured": row["dataTime"],
        "pm10": row.get("pm10Value"),
        "pm10_grade": grade("pm10", row.get("pm10Value"), row.get("pm10Grade")),
        "pm25": row.get("pm25Value"),
        "pm25_grade": grade("pm25", row.get("pm25Value"), row.get("pm25Grade")),
    }
