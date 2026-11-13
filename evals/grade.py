"""Automatic checks for one eval case.

Each case in cases.json may use:
  tools_all   tools that must be called at least once
  min_calls   {"tool": n}: call that tool at least n times
  args        {"tool": {"arg": regex}}: at least one call of that tool whose
              args all match (regex search on str(value))
  must        regexes the answer must match (each one)
  must_not    regexes the answer must NOT match
  grounded    every stop count, minute figure and won amount in the answer
              must appear in some tool result (the hallucination check)
  fail        tools that simulate an outage in this case (EVAL_FAIL)

A case passes only if every check passes. `notes` are for humans reading
the report; some behaviour (tone, assumptions) still needs a human look.
"""
import re

# Number followed by a unit we care about. Ranges like "30-35 min" count both ends.
NUMBER_PATTERNS = [
    ("stops", r"(\d+)(?:\s*(?:-|–|~|to|or)\s*(\d+))?\s*(?:stops?|stations?|정거장|개\s*역)"),
    ("minutes", r"(\d+)(?:\s*(?:-|–|~|to)\s*(\d+))?\s*(?:-?\s*min(?:ute)?s?\b|분)"),
    ("won", r"(\d[\d,]*)\s*(?:won|원|KRW)"),
    ("won", r"₩\s*(\d[\d,]*)"),
]


def _norm(n: str) -> str:
    return n.replace(",", "")


def claimed_numbers(answer: str) -> list[tuple[str, str]]:
    """[(kind, number)] for every stop count, minute figure and won amount."""
    out = []
    for kind, pat in NUMBER_PATTERNS:
        for m in re.finditer(pat, answer, re.I):
            out += [(kind, _norm(g)) for g in m.groups() if g]
    return out


def ungrounded(answer: str, results: list[str]) -> list[str]:
    """Claimed numbers that appear in no tool result."""
    haystack = _norm("\n".join(results))
    return [f"{n} {kind}" for kind, n in claimed_numbers(answer)
            if not re.search(rf"(?<!\d){re.escape(n)}(?!\d)", haystack)]


def grade(case: dict, answer: str, log: list) -> list[dict]:
    """Return [{"check", "ok", "detail"}] for this case. `log` is
    [(tool_name, args, result_text), ...] from briefing.llm.ask."""
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    called = [name for name, _, _ in log]
    for tool in case.get("tools_all", []):
        add(f"calls {tool}", tool in called, "" if tool in called else f"called: {called or 'nothing'}")
    for tool, n in case.get("min_calls", {}).items():
        k = called.count(tool)
        add(f"{tool} x{n}", k >= n, f"called {k}x")
    for tool, want in case.get("args", {}).items():
        calls = [args for name, args, _ in log if name == tool]
        ok = any(all(re.search(rx, str(args.get(arg, ""))) for arg, rx in want.items()) for args in calls)
        add(f"{tool} args", ok, "" if ok else f"wanted {want}, got {calls}")
    for rx in case.get("must", []):
        add(f"says /{rx}/", re.search(rx, answer), "")
    for rx in case.get("must_not", []):
        m = re.search(rx, answer)
        add(f"never says /{rx}/", not m, f"found {m.group(0)!r}" if m else "")
    if case.get("grounded"):
        bad = ungrounded(answer, [r for _, _, r in log])
        add("numbers grounded in tool results", not bad, ", ".join(bad))
    return checks
