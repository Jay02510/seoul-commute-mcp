"""Load API keys from .env. Fails loudly if a key is missing."""
import os

from dotenv import load_dotenv

load_dotenv()


def get_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is missing. Copy .env.example to .env and fill it in.")
    return value
