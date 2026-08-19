from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import requests


T = TypeVar("T")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, requests.Timeout, requests.ConnectionError)):
        return True
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status in RETRYABLE_STATUS:
        return True
    message = str(exc).casefold()
    return any(marker in message for marker in (" 429", " 500", "timeout", "timed out"))


async def with_backoff(
    operation: Callable[[], Awaitable[T]], *, attempts: int = 3,
    base_delay: float = 1.0, on_retry: Callable[[int, float, Exception], None] | None = None,
) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            if attempt >= attempts or not is_retryable(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, base_delay / 4)
            if on_retry:
                on_retry(attempt, delay, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("Retry terminou sem resultado.")
