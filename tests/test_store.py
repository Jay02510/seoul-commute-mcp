import sqlite3
from datetime import date, datetime

import pytest

from briefing import store

THU = date(2026, 11, 12)
SAT = date(2026, 11, 14)


@pytest.fixture
def con(tmp_path):
    return store.connect(tmp_path / "test.db")


def test_add_and_normalise(con):
    store.add_route(con, "work", "Mapo", "gangnam", "홍대입구역", "합정역", dest="강남역")
    r = store.get_route(con, "work")
    assert (r["home"], r["work"], r["station"], r["toward"], store.dest(r)) == \
        ("마포구", "강남구", "홍대입구", "합정", "강남")


def test_bad_day_and_district(con):
    with pytest.raises(ValueError, match="Unknown day"):
        store.add_route(con, "x", "Mapo", "Gangnam", "홍대입구", days="mon,funday")
    with pytest.raises(ValueError, match="Unknown Seoul district"):
        store.add_route(con, "y", "Bundang", "Gangnam", "홍대입구")


def test_set_dest(con):
    store.add_route(con, "work", "Mapo", "Gangnam", "홍대입구")
    assert store.dest(store.get_route(con, "work")) == ""
    assert store.set_dest(con, "work", "강남역")
    assert store.dest(store.get_route(con, "work")) == "강남"
    assert store.set_dest(con, "work", "")
    assert store.dest(store.get_route(con, "work")) == ""
    assert not store.set_dest(con, "nope", "강남")


def test_due_weekdays_and_send_log(con):
    store.add_route(con, "work", "Mapo", "Gangnam", "홍대입구")
    assert [r["name"] for r in store.due_routes(con, THU)] == ["work"]
    assert store.due_routes(con, SAT) == []
    store.mark_sent(con, store.get_route(con, "work")["id"], THU)
    assert store.due_routes(con, THU) == []          # idempotent: no second send


def test_migrates_old_db(tmp_path):
    """A briefing.db made before the dest column existed gets it added."""
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE routes (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
        home TEXT NOT NULL, work TEXT NOT NULL, station TEXT NOT NULL,
        toward TEXT NOT NULL DEFAULT '', days TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri',
        active INTEGER NOT NULL DEFAULT 1);
        INSERT INTO routes (name, home, work, station, toward) VALUES ('work', '마포구', '강남구', '홍대입구', '합정');""")
    old.commit()
    old.close()
    con = store.connect(path)
    r = store.get_route(con, "work")
    assert store.dest(r) == "" and r["toward"] == "합정"
    store.connect(path)                               # second connect: no error


def test_dest_on_plain_dict():
    assert store.dest({"name": "x"}) == ""
    assert store.dest({"dest": "강남"}) == "강남"


def test_send_time_window(con):
    store.add_route(con, "work", "Mapo", "Gangnam", "홍대입구")              # default 07:45
    store.add_route(con, "home", "Gangnam", "Mapo", "강남", at="18:00")
    names = lambda h, m: [r["name"] for r in store.due_routes(con, datetime(2026, 11, 12, h, m))]
    assert names(7, 44) == []
    assert names(7, 50) == ["work"]                 # the 07:45 job, a few minutes late
    assert names(10, 59) == ["work"]
    assert names(11, 0) == []                       # stale: more than 3 h 15 late
    assert names(17, 45) == []                      # 17:45 job is before 18:00
    assert names(18, 0) == ["home"]
    store.mark_sent(con, store.get_route(con, "home")["id"], THU)
    assert names(18, 5) == []


def test_set_time_and_bad_time(con):
    store.add_route(con, "home", "Gangnam", "Mapo", "강남", at="6:05")
    assert store.send_time(store.get_route(con, "home")) == "06:05"
    assert store.set_time(con, "home", "18:00")
    assert store.send_time(store.get_route(con, "home")) == "18:00"
    assert not store.set_time(con, "nope", "18:00")
    with pytest.raises(ValueError, match="Bad time"):
        store.set_time(con, "home", "6pm")
    with pytest.raises(ValueError, match="Bad time"):
        store.add_route(con, "x", "Mapo", "Gangnam", "홍대입구", at="25:00")


def test_migration_adds_send_time(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE routes (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
        home TEXT NOT NULL, work TEXT NOT NULL, station TEXT NOT NULL,
        toward TEXT NOT NULL DEFAULT '', dest TEXT NOT NULL DEFAULT '',
        days TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri', active INTEGER NOT NULL DEFAULT 1);
        INSERT INTO routes (name, home, work, station) VALUES ('work', '마포구', '강남구', '홍대입구');""")
    old.commit()
    old.close()
    assert store.send_time(store.get_route(store.connect(path), "work")) == "07:45"



def test_routes_file_and_window(tmp_path):
    from datetime import datetime
    path = tmp_path / "routes.json"
    path.write_text('[{"name": "work", "home": "Mapo", "work": "Gangnam", "station": "홍대입구역", '
                    '"toward": "합정", "dest": "강남"}, {"name": "home", "home": "Gangnam", '
                    '"work": "Mapo", "station": "강남", "at": "18:00"}]', encoding="utf-8")
    work, home = store.load_routes_file(path)
    assert (work["home"], work["station"], work["at"], store.dest(work)) == ("마포구", "홍대입구", "07:45", "강남")
    assert store.in_window(work, datetime(2026, 11, 13, 7, 46))       # Friday morning
    assert not store.in_window(home, datetime(2026, 11, 13, 7, 46))
    assert store.in_window(home, datetime(2026, 11, 13, 18, 1))
    assert not store.in_window(work, datetime(2026, 11, 14, 7, 46))   # Saturday


def test_routes_file_rejects_bad_day(tmp_path):
    path = tmp_path / "routes.json"
    path.write_text('[{"name": "x", "home": "Mapo", "work": "Gangnam", "station": "홍대입구", "days": "funday"}]',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="unknown day"):
        store.load_routes_file(path)


def test_repo_routes_file_is_valid():
    from pathlib import Path
    routes = store.load_routes_file(Path(__file__).parent.parent / "deploy" / "routes.json")
    assert [r["name"] for r in routes] == ["work", "home"]


def test_cloud_run_sends_only_due_routes(tmp_path, monkeypatch):
    import asyncio
    from datetime import datetime
    from briefing import main
    sent = []

    async def fake_build(route, writer="rules", verbose=False):
        return f"briefing {route['name']}"

    async def fake_send(text):
        sent.append(text)

    monkeypatch.setattr(main, "_build", fake_build)
    monkeypatch.setattr(main.telegram, "send", fake_send)
    monkeypatch.setattr(main.store, "kst_now", lambda: datetime(2026, 11, 13, 18, 0, 30))
    monkeypatch.setattr(main.store, "connect", lambda *a: (_ for _ in ()).throw(AssertionError("no DB in cloud")))
    routes = __import__("pathlib").Path(__file__).parent.parent / "deploy" / "routes.json"
    assert asyncio.run(main.cmd_run(False, "rules", str(routes))) == 0
    assert sent == ["briefing home"]
