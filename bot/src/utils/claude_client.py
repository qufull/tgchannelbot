from __future__ import annotations

import time
from typing import Optional

from src.utils.ai import get_model
from src.utils.config import settings

try:
    from anthropic import Anthropic
    from anthropic import RateLimitError, APIConnectionError, APITimeoutError, APIStatusError
except Exception:
    Anthropic = None
    RateLimitError = APIConnectionError = APITimeoutError = APIStatusError = Exception

_client: Optional["Anthropic"] = None


def get_claude() -> "Anthropic":
    global _client
    if Anthropic is None:
        raise RuntimeError("Пакет anthropic не установлен. Поставь anthropic в requirements.txt")
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY не задан в .env")
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def claude_rewrite(system: str, user: str, *, max_tokens: int = 900) -> str:
    """
    Синхронный вызов (его ты будешь запускать через asyncio.to_thread).
    """
    client = get_claude()

    last_err = None
    for attempt in range(5):
        try:
            resp = client.messages.create(
                model=get_model(),
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )

            parts = []
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    parts.append(block.text)
            return ("".join(parts)).strip()

        except (RateLimitError, APITimeoutError, APIConnectionError) as e:
            last_err = e
            time.sleep(0.6 * (2 ** attempt))  # backoff
        except APIStatusError as e:
            # 5xx — можно ретраить, 4xx — обычно нет смысла
            last_err = e
            if getattr(e, "status_code", 0) >= 500:
                time.sleep(0.6 * (2 ** attempt))
            else:
                break
        except Exception as e:
            last_err = e
            break
