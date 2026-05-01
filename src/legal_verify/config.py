from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Пути
ROOT_DIR    = Path(__file__).parent.parent.parent
PROMPTS_DIR = Path(__file__).parent / "prompts"
HISTORY_DIR = ROOT_DIR / "history"

HISTORY_DIR.mkdir(exist_ok=True)

# OpenAI
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
MODEL: str = os.getenv("MODEL", "gpt-5.4")

# Цикл верификации
MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "3"))

# Лимит mismatch-цитат для patch-режима (при превышении → полная регенерация)
PATCH_MAX_MISMATCHES: int = int(os.getenv("PATCH_MAX_MISMATCHES", "2"))

# Telegram
TELEGRAM_TOKEN: str | None = os.getenv("TELEGRAM_TOKEN")


def require_openai_api_key() -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required. Copy .env.example to .env and fill it.")
    return OPENAI_API_KEY
