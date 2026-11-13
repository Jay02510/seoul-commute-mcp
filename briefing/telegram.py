"""Minimal Telegram Bot API client: send a message, find your chat id."""
import httpx

from sources.config import get_key
from sources.http import ApiError

API = "https://api.telegram.org/bot{token}/{method}"


# Connect fast, but give Telegram time to answer; one retry on a timeout.
TIMEOUT = httpx.Timeout(30, connect=10)


async def _call(method: str, payload: dict | None = None) -> dict:
    url = API.format(token=get_key("TELEGRAM_BOT_TOKEN"), method=method)
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.post(url, json=payload or {})
            break
        except httpx.TimeoutException:
            if attempt == 2:
                raise ApiError(f"Telegram {method}: no answer from api.telegram.org "
                               "(timed out twice). Check your internet, then retry.") from None
        except httpx.HTTPError as e:  # DNS, refused, TLS...; never print the URL (it has the token)
            raise ApiError(f"Telegram {method}: {type(e).__name__}") from None
    if r.status_code in (401, 404):
        raise ApiError(f"Telegram {method}: bot token rejected ({r.status_code}). "
                       "Re-copy it from @BotFather into .env.")
    data = r.json()
    if not data.get("ok"):
        raise ApiError(f"Telegram {method}: {data.get('description', r.text[:200])}")
    return data["result"]


async def send(text: str) -> None:
    await _call("sendMessage", {
        "chat_id": get_key("TELEGRAM_CHAT_ID"),
        "text": text,
        "disable_web_page_preview": True,
    })


async def chat_ids() -> list[tuple[int, str]]:
    """Chats that have messaged the bot recently. Send your bot any message first."""
    updates = await _call("getUpdates")
    seen = {}
    for u in updates:
        chat = (u.get("message") or {}).get("chat")
        if chat:
            seen[chat["id"]] = chat.get("username") or chat.get("first_name") or chat.get("title", "")
    return list(seen.items())
