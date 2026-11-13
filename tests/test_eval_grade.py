"""The eval grader itself (evals/grade.py), so a broken check can't fake a score."""
import json
from pathlib import Path

from evals.grade import claimed_numbers, grade, ungrounded

ROUTE_RESULT = ("홍대입구 -> 강남: 38 min, 17 stops, 0 transfers, card fare 1,650 won. "
                "Departs 11:26, arrives 12:04 (timetable).")
LOG = [("route", {"from_station": "홍대입구", "to_station": "강남"}, ROUTE_RESULT)]


def test_claimed_numbers():
    text = "It's 17 stops, about 30-35 minutes, 1,650 won (₩1,650). 다음 열차 3분 후, 5정거장."
    assert claimed_numbers(text) == [("stops", "17"), ("stops", "5"), ("minutes", "30"), ("minutes", "35"),
                                     ("minutes", "3"), ("won", "1650"), ("won", "1650")]


def test_grounded_ok_and_invented():
    assert ungrounded("17 stops, 38 min, 1,650 won", [ROUTE_RESULT]) == []
    assert ungrounded("about 15 stops, 40 minutes", [ROUTE_RESULT]) == ["15 stops", "40 minutes"]
    assert ungrounded("17 stops", []) == ["17 stops"]          # no tool called: nothing is grounded
    assert ungrounded("1 stop", ["17 stops"]) == ["1 stops"]   # 1 is not part of 17
    assert ungrounded("about 16-17 stops", ["17 stops"]) == ["16 stops"]   # both ends of a range


def test_grade_all_checks():
    case = {"tools_all": ["route"], "args": {"route": {"from_station": "^홍대입구$"}},
            "min_calls": {"route": 1}, "must": ["(?i)stops"], "must_not": ["(?i)roughly"], "grounded": True}
    checks = grade(case, "17 stops, 38 min.", LOG)
    assert all(c["ok"] for c in checks) and len(checks) == 6
    bad = grade(case, "Roughly 15 stops.", [])
    assert [c["check"] for c in bad if not c["ok"]] == [
        "calls route", "route x1", "route args", "never says /(?i)roughly/", "numbers grounded in tool results"]


def test_cases_file_is_valid():
    cases = json.loads((Path(__file__).parent.parent / "evals" / "cases.json").read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 33 and [c["id"] for c in cases] == list(range(1, 34))
    tools = {"current_weather", "air_quality", "next_trains", "route", "list_districts", "forecast"}
    for c in cases:
        named = set(c.get("tools_all", [])) | set(c.get("min_calls", {})) | set(c.get("args", {})) | set(c.get("fail", []))
        assert named <= tools, c["id"]
        assert c.get("tools_all") or c.get("must") or c.get("grounded"), f"case {c['id']} checks nothing"
