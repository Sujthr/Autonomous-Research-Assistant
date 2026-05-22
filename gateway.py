"""
LLM gateway client with retry/backoff.

Re-exports LLM and ask from llm_gatewayV3, but wraps LLM.chat() so that
503 / 429 rate-limit responses are retried with exponential backoff instead
of immediately raising and forcing the agent into its dumb fallback heuristics.

Retry schedule (seconds): 5 → 10 → 20  (3 attempts, then re-raise)
"""
from __future__ import annotations

import sys
import time
import logging
from pathlib import Path

_GATEWAY = Path(__file__).parent / "5e4a8833-292d-4ce5-be97-749c7656bdbf" / "llm_gatewayV3"
if str(_GATEWAY) not in sys.path:
    sys.path.append(str(_GATEWAY))

from client import LLM as _BaseLLM, ask as _base_ask  # noqa: E402

log = logging.getLogger(__name__)

_RETRY_DELAYS = (5, 10, 20)   # seconds between attempts after a rate-limit hit
_RETRY_STATUS  = {429, 503}   # HTTP status codes that warrant a retry


class LLM(_BaseLLM):
    """LLM gateway client with automatic retry on rate-limit (503/429)."""

    def chat(self, *args, **kwargs):
        import httpx
        last_exc: Exception | None = None
        for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
            try:
                return super().chat(*args, **kwargs)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRY_STATUS or delay is None:
                    raise
                last_exc = exc
                log.warning(
                    "[gateway] HTTP %d on attempt %d — retrying in %ds",
                    exc.response.status_code, attempt, delay,
                )
                time.sleep(delay)
            except Exception:
                raise   # connection errors, parse errors — don't retry
        raise last_exc  # type: ignore[misc]


def ask(prompt: str, provider: str | None = None, **kw) -> str:
    return LLM().chat(prompt, provider=provider, **kw)["text"]


__all__ = ["LLM", "ask"]
