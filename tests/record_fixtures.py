"""Record real API replies into tests/fixtures/live/ (run on the Mac, needs .env keys).

    uv run python tests/record_fixtures.py

Calls each source once through its normal code, saves the raw JSON reply the
parser saw, and prints what was saved. Replies contain no API keys. Then
`uv run pytest` also checks the parsers against these real replies
(tests/test_live_fixtures.py); without them those tests are skipped.
Uses 5 data.go.kr calls and 1 Seoul subway call.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sources import airkorea, http, kma, route, subway  # noqa: E402

OUT = Path(__file__).parent / "fixtures" / "live"


def recorder(module, name: str):
    real = http.get_json

    async def get_json(url, params=None):
        reply = await real(url, params)
        (OUT / f"{name}.json").write_text(json.dumps(reply, ensure_ascii=False, indent=1), encoding="utf-8")
        return reply

    module.get_json = get_json


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("kma", kma, lambda: kma.current("Mapo")),
        ("kma_forecast", kma, lambda: kma.forecast("Mapo", 24)),
        ("airkorea", airkorea, lambda: airkorea.current("Mapo")),
        ("subway", subway, lambda: subway.arrivals("홍대입구")),
        ("route", route, lambda: route.find("공덕", "강남")),   # 2 transfers
    ]
    failed = 0
    for name, module, call in jobs:
        recorder(module, name)
        try:
            await call()
            print(f"saved {name}.json")
        except Exception as e:
            failed += 1
            print(f"FAILED {name}: {type(e).__name__}: {str(e)[:120]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
