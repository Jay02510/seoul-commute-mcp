"""Diagnostic: Gemini with NO MCP server.

1. Lists the Flash models your key can use (pick backups for GEMINI_MODEL).
2. Sends one tiny request to each model in GEMINI_MODEL (or the default).

    uv run python scripts/debug_gemini.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for `sources`
import asyncio
import os
import time

from google import genai

import sources.config  # noqa: F401  (loads .env)
from briefing.llm import gemini_models


async def main():
    api = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    print("Flash models available to your key:")
    async for m in await api.aio.models.list():
        name = m.name.removeprefix("models/")
        if "flash" in name and "generateContent" in (m.supported_actions or []):
            print("  ", name)
    for model in gemini_models():
        t = time.time()
        try:
            r = await asyncio.wait_for(api.aio.models.generate_content(
                model=model, contents="Reply with exactly: pong"), 60)
            print(f"{model}: OK in {time.time() - t:.1f}s -> {r.text!r}")
        except Exception as e:
            print(f"{model}: FAILED after {time.time() - t:.1f}s -> {type(e).__name__}: {str(e)[:160]}")


asyncio.run(main())
