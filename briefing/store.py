"""SQLite state for the briefing: saved routes and a log of what was sent.

The send log stops duplicates: if launchd fires twice in one day (e.g. after
the Mac wakes from sleep), each route is still sent only once.
"""
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sources.districts import resolve

DB_PATH = Path(__file__).resolve().parent.parent / "briefing.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS routes (
    id      INTEGER PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL,
    home    TEXT NOT NULL,              -- district at the start (weather, air)
    work    TEXT NOT NULL,              -- district at the destination
    station TEXT NOT NULL,              -- boarding station, Korean, no '역'
    toward  TEXT NOT NULL DEFAULT '',   -- direction keyword, e.g. '합정' or '성수'
    dest    TEXT NOT NULL DEFAULT '',   -- destination station for the journey line, e.g. '강남'
    days    TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri',
    at      TEXT NOT NULL DEFAULT '07:45',  -- send time HH:MM (launchd must fire at or after it)
    active  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sent_log (
    route_id INTEGER NOT NULL,
    day      TEXT NOT NULL,             -- YYYY-MM-DD
    sent_at  TEXT NOT NULL,
    PRIMARY KEY (route_id, day)
);
"""

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con


def _migrate(con) -> None:
    """Add columns that older briefing.db files don't have yet.
    CREATE TABLE IF NOT EXISTS leaves an existing table untouched."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(routes)")}
    if "dest" not in cols:
        con.execute("ALTER TABLE routes ADD COLUMN dest TEXT NOT NULL DEFAULT ''")
        con.commit()
    if "at" not in cols:
        con.execute("ALTER TABLE routes ADD COLUMN at TEXT NOT NULL DEFAULT '07:45'")
        con.commit()


def _station(name: str) -> str:
    return name.strip().removesuffix("역")


# A briefing that arrives this long after its time is stale (the Mac woke late):
# skip it. 07:45 + 3 h 15 = 11:00, the old fixed cut-off.
LATE_WINDOW = timedelta(hours=3, minutes=15)


KST = ZoneInfo("Asia/Seoul")


def kst_now() -> datetime:
    """Seoul wall-clock time without tzinfo. On the Mac this is just now();
    in a Cloud Run container (UTC) it keeps send windows and 'today' right."""
    return datetime.now(KST).replace(tzinfo=None)


def in_window(route, now: datetime) -> bool:
    """True from the route's send time until LATE_WINDOW after it, on its days."""
    if WEEKDAYS[now.weekday()] not in route["days"].split(","):
        return False
    start = datetime.combine(now.date(), datetime.strptime(send_time(route), "%H:%M").time())
    return start <= now < start + LATE_WINDOW


def load_routes_file(path) -> list[dict]:
    """Routes from a JSON file (for the cloud job, which has no briefing.db):
    a list of objects with name, home, work, station and optional toward,
    dest, days, at. Normalised the same way as add_route."""
    out = []
    for r in json.loads(Path(path).read_text(encoding="utf-8")):
        days = [d.strip().lower()[:3] for d in r.get("days", "mon,tue,wed,thu,fri").split(",") if d.strip()]
        bad = [d for d in days if d not in WEEKDAYS]
        if bad:
            raise ValueError(f"route {r.get('name')!r}: unknown day(s) {bad}")
        out.append({"id": None, "name": r["name"], "home": resolve(r["home"]), "work": resolve(r["work"]),
                    "station": _station(r["station"]), "toward": _station(r.get("toward", "")),
                    "dest": _station(r.get("dest", "")), "days": ",".join(days),
                    "at": check_time(r.get("at", "07:45")), "active": 1})
    return out


def check_time(at: str) -> str:
    """'7:45' -> '07:45'; raises ValueError for anything that isn't a clock time."""
    try:
        return datetime.strptime(at.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        raise ValueError(f"Bad time {at!r}: use HH:MM, e.g. 07:45 or 18:00") from None


def send_time(route) -> str:
    """Send time of a route row (or a plain dict in tests), '07:45' if none."""
    return route["at"] if "at" in route.keys() else "07:45"


def dest(route) -> str:
    """Destination station of a route row (or a plain dict in tests), '' if none."""
    return route["dest"] if "dest" in route.keys() else ""


def add_route(con, name: str, home: str, work: str, station: str,
              toward: str = "", days: str = "mon,tue,wed,thu,fri", dest: str = "",
              at: str = "07:45") -> None:
    day_list = [d.strip().lower()[:3] for d in days.split(",") if d.strip()]
    bad = [d for d in day_list if d not in WEEKDAYS]
    if bad:
        raise ValueError(f"Unknown day(s) {bad}. Use mon,tue,wed,thu,fri,sat,sun.")
    con.execute(
        "INSERT INTO routes (name, home, work, station, toward, days, dest, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, resolve(home), resolve(work), _station(station),
         _station(toward), ",".join(day_list), _station(dest), check_time(at)),
    )
    con.commit()


def set_dest(con, name: str, station: str) -> bool:
    """Set (or clear, with '') the destination station of a saved route."""
    cur = con.execute("UPDATE routes SET dest = ? WHERE name = ?", (_station(station), name))
    con.commit()
    return cur.rowcount > 0


def set_time(con, name: str, at: str) -> bool:
    """Change a saved route's send time (HH:MM)."""
    cur = con.execute("UPDATE routes SET at = ? WHERE name = ?", (check_time(at), name))
    con.commit()
    return cur.rowcount > 0


def remove_route(con, name: str) -> bool:
    cur = con.execute("DELETE FROM routes WHERE name = ?", (name,))
    con.commit()
    return cur.rowcount > 0


def list_routes(con) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM routes ORDER BY id").fetchall()


def get_route(con, name: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM routes WHERE name = ?", (name,)).fetchone()


def due_routes(con, now: date | datetime) -> list[sqlite3.Row]:
    """Active routes for today's weekday that haven't been sent today.

    With a datetime, a route is also only due from its send time until
    LATE_WINDOW after it, so one launchd job firing at 07:45 and 17:45 sends
    the morning route in the morning and the evening route in the evening.
    With a plain date the time of day is ignored.
    """
    today = now.date() if isinstance(now, datetime) else now
    wd = WEEKDAYS[today.weekday()]
    rows = con.execute(
        "SELECT * FROM routes r WHERE active = 1 AND NOT EXISTS "
        "(SELECT 1 FROM sent_log s WHERE s.route_id = r.id AND s.day = ?)",
        (today.isoformat(),),
    ).fetchall()
    rows = [r for r in rows if wd in r["days"].split(",")]
    if isinstance(now, datetime):
        rows = [r for r in rows if in_window(r, now)]
    return rows


def mark_sent(con, route_id: int, today: date) -> None:
    con.execute(
        "INSERT OR REPLACE INTO sent_log (route_id, day, sent_at) VALUES (?, ?, ?)",
        (route_id, today.isoformat(), datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()
