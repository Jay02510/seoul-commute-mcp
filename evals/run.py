"""Run the eval set (33 questions) against the MCP server with a real model.

    uv run python -m evals.run                    # all cases
    uv run python -m evals.run --only 17,23,27    # some cases (ranges work too: --only 11-21)
    uv run python -m evals.run --category route   # one category
    uv run python -m evals.run --with-instructions   # also give the model the server instructions
    uv run python -m evals.run --rerun evals/results/2026-11-12_1500.json   # redo only the errors

Each case starts server.py (through briefing.llm.ask, the same MCP client and
tool-use loop as the LLM briefing), asks the question, and grades the answer
and tool calls with evals/grade.py. Cases with "fail" set start the server
with EVAL_FAIL so those tools simulate an outage.

Results go to evals/results/<date>_<time>.json (everything, incl. answers and
tool results) and .md (readable report). Both are rewritten after every case,
so a run stopped halfway (Ctrl-C, network drop) keeps what it finished.
--rerun FILE repeats the cases that ended in `error` (or the --only ids) and
writes a merged report as a new file. Provider and model come from .env,
as for the briefing. Costs roughly 30-60 model calls and ~100 API calls.
"""
import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from briefing import llm
from evals.grade import grade

HERE = Path(__file__).parent
KST = ZoneInfo("Asia/Seoul")

# Deliberately plain, like a general chat app: the tools must carry the rules.
SYSTEM = """You are a helpful assistant. You have tools with live Seoul weather,
air quality and subway data. Current time: {now} KST. Answer the user's
question briefly and clearly, in the user's language."""


def load_cases(only: set[int] | None, category: str | None) -> list[dict]:
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
    return [c for c in cases
            if (not only or c["id"] in only) and (not category or c["category"] == category)]


def regrade(r: dict) -> dict:
    """Re-check an earlier answer against the current cases.json, so a rerun's
    merged report uses today's checks for the cases it doesn't repeat."""
    if r["status"] == "error":
        return r
    case = next((c for c in load_cases({r["id"]}, None)), None)
    if not case:
        return r
    log = [(t["name"], t["args"], t["result"]) for t in r["tools"]]
    checks = grade(case, r["answer"], log)
    return {**r, **case, "checks": checks, "status": "pass" if all(c["ok"] for c in checks) else "fail"}


QUOTA_STOP = 3   # daily-quota errors in a row before the run stops


def quota_hit(r: dict) -> bool:
    """True for an error caused by a used-up quota (429), not a one-off 503."""
    err = r.get("error", "")
    return r["status"] == "error" and ("429" in err or "RESOURCE_EXHAUSTED" in err)


def parse_ids(text: str) -> set[int]:
    """'11-14,20' -> {11, 12, 13, 14, 20}."""
    ids: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            ids.update(range(min(a, b), max(a, b) + 1))
        else:
            ids.add(int(part))
    return ids


def not_run(case: dict) -> dict:
    """Placeholder for a case skipped after the quota ran out, so --rerun picks it up."""
    return {**case, "status": "error", "error": "not run: daily quota reached", "model": None,
            "seconds": 0, "checks": [], "tools": []}


def server_instructions() -> str:
    sys.path.insert(0, str(HERE.parent))
    import server  # noqa: E402  (only for the INSTRUCTIONS text)
    return server.INSTRUCTIONS


async def run_case(case: dict, system: str, verbose: bool) -> dict:
    env = {"EVAL_FAIL": ",".join(case["fail"])} if case.get("fail") else None
    started = time.monotonic()
    try:
        answer, log = await llm.ask(system, case["question"], verbose=verbose, extra_env=env,
                                    max_tokens=800)
    except Exception as e:
        log = getattr(e, "tool_log", [])
        return {**case, "status": "error", "error": f"{type(e).__name__}: {e}", "model": llm.LAST_MODEL,
                "seconds": round(time.monotonic() - started, 1), "checks": [],
                "tools": [{"name": n, "args": a, "result": r} for n, a, r in log]}
    checks = grade(case, answer, log)
    return {**case, "status": "pass" if all(c["ok"] for c in checks) else "fail",
            "answer": answer, "model": llm.LAST_MODEL,
            "tools": [{"name": n, "args": a, "result": r} for n, a, r in log],
            "checks": checks, "seconds": round(time.monotonic() - started, 1)}


def report_md(results: list[dict], meta: dict) -> str:
    graded = [r for r in results if r["status"] != "error"]
    passed = sum(r["status"] == "pass" for r in results)
    lines = [f"# Eval run {meta['started']}", "",
             f"- Provider / model: {meta['provider']} / {', '.join(sorted(meta['models'])) or '?'}",
             f"- Server instructions given to the model: {'yes' if meta['with_instructions'] else 'no'}",
             f"- **Score: {passed}/{len(results)} passed**"
             + (f" ({len(results) - len(graded)} errors, not graded)" if len(graded) < len(results) else ""),
             "", "| Category | Passed |", "|---|---|"]
    cats = Counter(r["category"] for r in results)
    for cat in cats:
        ok = sum(r["status"] == "pass" for r in results if r["category"] == cat)
        lines.append(f"| {cat} | {ok}/{cats[cat]} |")
    lines += ["", "| # | Category | Question | Result | Tools called | Failed checks |", "|---|---|---|---|---|---|"]
    for r in results:
        verdict = {"pass": "✅ pass", "fail": "❌ fail", "error": "⚠️ error"}[r["status"]]
        tools = ", ".join(t["name"] for t in r["tools"]) or "-"
        failed = "; ".join(f"{c['check']}" + (f" ({c['detail']})" if c["detail"] else "")
                           for c in r["checks"] if not c["ok"]) or r.get("error", "")
        lines.append(f"| {r['id']} | {r['category']} | {r['question']} | {verdict} | {tools} | "
                     f"{failed.replace('|', '/')} |")
    lines += ["", "## Answers", ""]
    for r in results:
        lines += [f"### {r['id']}. {r['question']}", ""]
        if r.get("notes"):
            lines += [f"*Expected:* {r['notes']}", ""]
        if r.get("fail"):
            lines += [f"*Simulated outage:* {', '.join(r['fail'])}", ""]
        lines += ["```", r.get("answer") or r.get("error", ""), "```", ""]
    return "\n".join(lines)


async def main() -> int:
    p = argparse.ArgumentParser(prog="evals.run")
    p.add_argument("--only", help="case ids, e.g. 17,23,27 or 11-21")
    p.add_argument("--category", help="weather, air, trains, route, commute, coverage, failure")
    p.add_argument("--delay", type=float, default=4.0, help="seconds between cases (free-tier rate limits)")
    p.add_argument("--with-instructions", action="store_true",
                   help="append the server instructions to the system prompt")
    p.add_argument("--rerun", metavar="FILE", help="earlier results .json: redo its error cases "
                   "(or the --only ids) and save a merged report")
    p.add_argument("-v", "--verbose", action="store_true", help="live tool-call trace")
    args = p.parse_args()

    only = parse_ids(args.only) if args.only else None
    previous: dict[int, dict] = {}
    if args.rerun:
        old = json.loads(Path(args.rerun).read_text(encoding="utf-8"))
        previous = {r["id"]: regrade(r) for r in old["results"]}
        if only is None:
            only = {i for i, r in previous.items() if r["status"] == "error"}
            if not only:
                print("No error cases in that file. Use --only to pick cases to redo.")
                return 1
        args.with_instructions = old["meta"].get("with_instructions", args.with_instructions)
    cases = load_cases(only, args.category)
    if not cases:
        print("No matching cases.")
        return 1
    now = datetime.now(KST)
    system = SYSTEM.format(now=f"{now:%a %Y-%m-%d %H:%M}")
    if args.with_instructions:
        system += "\n\n" + server_instructions()
    import sources.config  # noqa: F401  (loads .env so pick_provider sees the keys)
    meta = {"started": f"{now:%Y-%m-%d %H:%M}", "provider": llm.pick_provider(),
            "with_instructions": args.with_instructions, "models": set()}

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stem = out / f"{now:%Y-%m-%d_%H%M}"
    k = 1
    while stem.with_suffix(".json").exists():   # never overwrite an earlier run (e.g. the one being rerun)
        k += 1
        stem = out / f"{now:%Y-%m-%d_%H%M}-{k}"
    results = []

    def save():
        merged = {**previous, **{r["id"]: r for r in results}}
        rows = [merged[i] for i in sorted(merged)]
        if previous:
            for r in previous.values():
                if r.get("model"):
                    meta["models"].add(r["model"])
        stem.with_suffix(".json").write_text(json.dumps(
            {"meta": {**meta, "models": sorted(meta["models"]), "rerun_of": args.rerun}, "results": rows},
            ensure_ascii=False, indent=1), encoding="utf-8")
        stem.with_suffix(".md").write_text(report_md(rows, meta), encoding="utf-8")
        return rows

    streak = 0
    for i, case in enumerate(cases):
        if streak >= QUOTA_STOP:
            # Free-tier daily quota is gone: the rest would only collect 429s.
            results.extend(not_run(c) for c in cases[i:])
            rows = save()
            print(f"\nStopped: {QUOTA_STOP} quota errors in a row (429). "
                  f"{len(cases) - i} cases not run; try again after the quota resets.")
            break
        if i:
            await asyncio.sleep(args.delay)
        r = await run_case(case, system, args.verbose)
        streak = streak + 1 if quota_hit(r) else 0
        if r.get("model"):
            meta["models"].add(r["model"])
        results.append(r)
        mark = {"pass": "PASS", "fail": "FAIL", "error": "ERR "}[r["status"]]
        why = "; ".join(c["check"] for c in r["checks"] if not c["ok"]) or r.get("error", "")
        print(f"{mark} #{r['id']:>2} {r['category']:<8} {r['seconds']:>5}s  {r['question'][:55]}"
              + (f"  [{why[:90]}]" if why else ""), flush=True)
        rows = save()

    passed = sum(r["status"] == "pass" for r in rows)
    errors = sum(r["status"] == "error" for r in rows)
    print(f"\n{passed}/{len(rows)} passed" + (f", {errors} errors (redo with --rerun "
          f"{stem.with_suffix('.json').relative_to(HERE.parent)})" if errors else "")
          + f". Report: {stem.with_suffix('.md').relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
