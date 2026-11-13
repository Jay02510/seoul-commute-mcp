"""Diagnostic: call the Seoul Metro shortest-path API once and save the raw reply.

API: 서울교통공사_최단경로이동정보 (data.go.kr 15143842).
Apply for it on data.go.kr first (활용신청); it uses the same DATA_GO_KR_KEY.

    uv run python debug_route.py                 # 홍대입구 -> 강남
    uv run python debug_route.py 공덕 강남
    uv run python debug_route.py 0239 0222 --code   # by station code (0239 = Line 2 no. 239)

Writes logs/route_sample.json so the parser in sources/route.py can be built
against the real response shape. The key is never printed.
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

from sources.config import get_key

URL = "https://apis.data.go.kr/B553766/path2/getShtrmPath2"


async def main(src: str, dst: str, by_code: bool = False) -> None:
    params = {
        "serviceKey": get_key("DATA_GO_KR_KEY"),
        "dataType": "JSON",
        "dptreStn": src,
        "arvlStn": dst,
        "searchDt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "searchType": "duration",
        "stationValueType": "code" if by_code else "name",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(URL, params=params)
    print(f"HTTP {r.status_code}, {len(r.text)} chars")
    text = r.text.strip()
    if not text.startswith("{"):
        print("Not JSON (usually: API not approved yet, or key not active):")
        print(text[:500])
        return
    out = Path("logs/route_sample.json")
    out.write_text(json.dumps(r.json(), ensure_ascii=False, indent=2))
    body = r.json().get("body") or {}
    print(f"Saved {out}. Result: {r.json().get('header')}")
    for p in body.get("paths", []):
        a, b = p["dptreStn"], p["arvlStn"]
        print(f"  {a['stnNm']} {a['lineNm']} ({a['stnCd']}) -> {b['stnNm']} {b['lineNm']} ({b['stnCd']})"
              f"  {p['reqHr']}s{'  TRANSFER' if p['trsitYn'] == 'Y' else ''}")


if __name__ == "__main__":
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")] or ["홍대입구", "강남"]
    asyncio.run(main(args[0], args[1], "--code" in flags))
