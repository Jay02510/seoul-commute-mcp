"""LLM writer for the morning briefing.

Unlike `compose.py`, this does NOT call `sources/` directly. It starts our own
MCP server (`server.py`) as a subprocess, asks it which tools it has, and lets
the model decide which tools to call. That is the "agent on top of the MCP
server" part of the project.

Two providers, same loop:
  - Anthropic (Claude)  needs ANTHROPIC_API_KEY  (prepaid credits)
  - Google (Gemini)     needs GEMINI_API_KEY     (free tier in AI Studio)

Pick one with LLM_PROVIDER=anthropic|gemini in .env. If unset, whichever key is
present is used (Anthropic first). Model names can be overridden with
ANTHROPIC_MODEL / GEMINI_MODEL. GEMINI_MODEL may be a comma-separated list:
if one model is overloaded (503) or rate-limited (429), the next is tried.
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp import Client, StdioServerParameters

from sources.districts import DISTRICTS

ROOT = Path(__file__).resolve().parent.parent
MAX_ROUNDS = 6          # model turns; each turn may call several tools at once
MAX_TOKENS = 600        # a Telegram briefing is short
MODEL_TIMEOUT = 60      # seconds per model call; a hang becomes a clear error
DEFAULT_MODELS = {"anthropic": "claude-haiku-5-5", "gemini": "gemini-3.8-flash"}


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- prompt

SYSTEM = """You write a short morning commute briefing for one person in Seoul.
It is sent as a plain-text Telegram message, read on a phone in a few seconds.

Use the tools to get LIVE data before writing. For this route, check:
- weather at BOTH the home and work districts
- `forecast` at BOTH districts (rain later today, e.g. on the way home)
- air quality at BOTH districts
- next trains at the boarding station (filter to the direction keyword, if given)
- if a destination station is given: `route` from the boarding station to it,
  then one journey line (minutes, stops, transfers) using only the tool's numbers
Call independent tools in the same turn when you can.

Advice rules (from the rule-based writer, keep them):
- Umbrella if it is raining or snowing now at either end, or if `forecast`
  says rain is likely later (say from what time).
- Clothing by temperature: below 0°C heavy coat and gloves; below 5°C warm coat;
  below 12°C jacket; 28°C or more carry water. Wind 9 m/s or more: mention it.
- Mask if PM10 or PM2.5 is 'bad' or 'very bad' at either end.

Honesty rules (most important):
- If a tool returns an error or no data, say that part is unavailable.
  NEVER give reassuring advice ("no umbrella needed", "air is fine") about
  something you could not check.
- Journey times and stop counts may only come from the `route` tool. Never
  invent or estimate them. Later weather only from the `forecast` tool; if it failed, say the forecast is unavailable.
- Do not invent numbers. Only use values the tools returned.

Format:
- First line: "🚇 {name}: {home} → {work} · {time}"
- Then 3-7 short lines: weather, air, next 2-3 trains, the journey line (if any), and the advice.
- Plain text, a few emoji are fine, no Markdown (no **bold**, no # headings).
- Under 600 characters. English, but keep Korean station and direction names.
- Output only the message text, nothing before or after it."""


def dest_of(route) -> str:
    return route["dest"] if "dest" in route.keys() else ""


def _short(district: str) -> str:
    return DISTRICTS[district][0] if district in DISTRICTS else district


def user_prompt(route, now: datetime) -> str:
    toward = route["toward"] or "(none: show all directions)"
    return (
        f"Write today's briefing.\n"
        f"Now: {now:%a %Y-%m-%d %H:%M} KST\n"
        f"Route name: {route['name']}\n"
        f"Home district: {_short(route['home'])} ({route['home']})\n"
        f"Work district: {_short(route['work'])} ({route['work']})\n"
        f"Boarding station: {route['station']}\n"
        f"Direction keyword: {toward}\n"
        f"Destination station: {dest_of(route) or '(none: no journey line)'}"
    )


# ---------------------------------------------------------------- MCP side

def server_params(extra_env: dict | None = None) -> StdioServerParameters:
    # Same interpreter that runs us (uv's .venv), so server.py finds its deps.
    # cwd=ROOT so server.py's load_dotenv() finds .env: the MCP SDK passes only
    # a minimal environment (PATH, HOME, ...) to the subprocess, not our keys.
    # SERVER_LOG: server.py sends its stderr there, so a crash is visible.
    log = ROOT / "logs" / "mcp-server.log"
    log.parent.mkdir(exist_ok=True)
    return StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], cwd=ROOT,
                                 env={"SERVER_LOG": str(log), **(extra_env or {})})


def result_text(result) -> str:
    """Flatten a CallToolResult into plain text for the model."""
    parts = [getattr(c, "text", "") for c in result.content]
    text = "\n".join(p for p in parts if p) or "(empty result)"
    return f"Error: {text}" if result.is_error and not text.startswith("Error") else text


VERBOSE = False
LAST_MODEL = ""   # model that answered the last call (for eval reports)


def trace(msg: str) -> None:
    """Live progress on stderr with -v, so a hang or crash shows where it happened."""
    if VERBOSE:
        print(f"[llm {datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


async def call_tool(client: Client, name: str, args: dict, log: list) -> str:
    trace(f"→ {name}({args})")
    try:
        text = result_text(await client.call_tool(name, args))
    except Exception as e:  # protocol error, unknown tool, ...: tell the model
        text = f"Error: {type(e).__name__}: {e}"
    trace(f"← {text[:800]!r}")  # long enough to check every train the model quotes
    log.append((name, args, text))
    return text


# ---------------------------------------------------------------- providers

async def _timed(coro):
    try:
        return await asyncio.wait_for(coro, MODEL_TIMEOUT)
    except TimeoutError:
        raise LLMError(f"model did not answer within {MODEL_TIMEOUT}s") from None


async def _run_anthropic(client: Client, tools, system: str, prompt: str, log: list,
                         max_tokens: int = MAX_TOKENS) -> str:
    import anthropic

    model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODELS["anthropic"]
    api = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY
    spec = [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in tools]
    messages = [{"role": "user", "content": prompt}]
    for _ in range(MAX_ROUNDS):
        trace(f"asking {model}")
        global LAST_MODEL
        LAST_MODEL = model
        resp = await _timed(api.messages.create(model=model, max_tokens=max_tokens, system=system,
                                                tools=spec, messages=messages))
        trace(f"reply: stop={resp.stop_reason}")
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                text = await call_tool(client, b.name, b.input, log)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": text,
                                "is_error": text.startswith("Error")})
        messages.append({"role": "user", "content": results})
    raise LLMError(f"no final answer after {MAX_ROUNDS} rounds")


async def _run_gemini(client: Client, tools, system: str, prompt: str, log: list,
                      max_tokens: int = MAX_TOKENS) -> str:
    from google import genai
    from google.genai import types

    models = gemini_models()
    # The SDK retries 429/5xx with long backoff by default, which looked like a
    # hang. Retry briefly, then move on to the next model in the list.
    api = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=2, initial_delay=2, max_delay=5)))
    decls = [types.FunctionDeclaration(name=t.name, description=t.description or "",
                                       parameters_json_schema=t.input_schema) for t in tools]
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens * 4,  # Gemini counts thinking tokens here too
        tools=[types.Tool(function_declarations=decls)],
        # We run the loop ourselves (same as the Anthropic path), so turn off
        # the SDK's automatic function calling.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    for _ in range(MAX_ROUNDS):
        resp = await _gemini_call(api, models, contents, config)
        trace(f"reply: {len(resp.function_calls or [])} tool calls, "
              f"finish={resp.candidates[0].finish_reason if resp.candidates else '?'}")
        calls = resp.function_calls or []
        if not calls:
            if not resp.text:
                raise LLMError(f"empty reply (finish reason: {resp.candidates[0].finish_reason if resp.candidates else '?'})")
            return resp.text
        # Send the model's turn back unchanged: it carries "thought signatures"
        # that Gemini needs to continue its reasoning.
        contents.append(resp.candidates[0].content)
        parts = []
        for c in calls:
            text = await call_tool(client, c.name, dict(c.args or {}), log)
            parts.append(types.Part.from_function_response(name=c.name, response={"result": text}))
        contents.append(types.Content(role="user", parts=parts))
    raise LLMError(f"no final answer after {MAX_ROUNDS} rounds")


def gemini_models() -> list[str]:
    raw = os.environ.get("GEMINI_MODEL") or DEFAULT_MODELS["gemini"]
    return [m.strip() for m in raw.split(",") if m.strip()]


RETRYABLE = {429, 500, 502, 503, 504}  # overloaded / rate-limited / server hiccup


async def _gemini_call(api, models: list[str], contents, config):
    """One model turn, trying each model in order until one answers."""
    from google.genai import errors

    last = None
    for model in models:
        trace(f"asking {model}")
        try:
            resp = await _timed(api.aio.models.generate_content(model=model, contents=contents, config=config))
            global LAST_MODEL
            LAST_MODEL = model
            return resp
        except errors.APIError as e:
            if e.code not in RETRYABLE:
                raise
            last = f"{model}: {e.code} {e.status}"
        except LLMError as e:  # timeout
            last = f"{model}: {e}"
        trace(f"failed ({last}), trying next model")
    raise LLMError(f"all Gemini models busy or failing; last: {last}")


PROVIDERS = {"anthropic": _run_anthropic, "gemini": _run_gemini}
KEY_NAMES = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


def pick_provider() -> str:
    chosen = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if chosen:
        if chosen not in PROVIDERS:
            raise LLMError(f"LLM_PROVIDER={chosen!r}: use 'anthropic' or 'gemini'")
        if not os.environ.get(KEY_NAMES[chosen], "").strip():
            raise LLMError(f"LLM_PROVIDER={chosen} but {KEY_NAMES[chosen]} is empty in .env")
        return chosen
    for name, key in KEY_NAMES.items():
        if os.environ.get(key, "").strip():
            return name
    raise LLMError("no LLM key: set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env")


# ---------------------------------------------------------------- entry point

def unwrap(e: BaseException) -> BaseException:
    """Dig the first real error out of (nested) ExceptionGroups."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


async def ask(system: str, prompt: str, verbose: bool = False, extra_env: dict | None = None,
              max_tokens: int = MAX_TOKENS) -> tuple[str, list]:
    """Run one question through the tool-use loop against our own MCP server.
    Returns (final text, tool log as [(name, args, result_text), ...]).
    Raises on any failure. Used by the briefing and by evals/run.py."""
    import sources.config  # noqa: F401  (loads .env)

    global VERBOSE
    VERBOSE = verbose
    provider = pick_provider()
    log: list = []
    error = None
    text = ""
    try:
        trace("starting server.py")
        async with Client(server_params(extra_env)) as client:
            tools = (await client.list_tools()).tools
            trace(f"tools: {[t.name for t in tools]}")
            # Catch inside the block: an exception escaping the MCP client's task
            # group comes out wrapped in an ExceptionGroup, which is hard to read.
            try:
                text = await PROVIDERS[provider](client, tools, system, prompt, log, max_tokens)
            except Exception as e:
                error = e
            trace(f"closing server ({'error: ' + type(error).__name__ if error else 'ok'})")
    except BaseExceptionGroup as eg:  # failure while starting/stopping the server
        # If the model call already failed, that is the real cause; a
        # "Connection closed" from shutting the server down is just noise.
        raise (error or unwrap(eg)) from eg
    if error:
        error.tool_log = log   # evals show which tools ran before the failure
        raise error
    trace(f"done: provider={provider}, {len(log)} tool calls")
    text = text.strip()
    if not text:
        raise LLMError("model returned empty text")
    return text, log


async def write(route, now: datetime | None = None, verbose: bool = False) -> str:
    """Return the briefing text written by the LLM. Raises on any failure, so
    the caller can fall back to the rule-based writer."""
    now = now or datetime.now()
    text, _ = await ask(SYSTEM, user_prompt(route, now), verbose=verbose)
    return text
