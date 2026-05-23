"""Retry helper used around external/provider calls."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from ai.providers.base import ProviderError

T = TypeVar("T")
logger = logging.getLogger(__name__)


async def run_with_retries(
    operation: str,
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int,
) -> T:
    retryer = AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=0.1, max=2.0),
        retry=retry_if_exception_type((ProviderError, TimeoutError, OSError)),
        reraise=True,
    )
    async for attempt in retryer:
        with attempt:
            try:
                return await call()
            except Exception:
                logger.warning("external_call_failed", extra={"operation": operation})
                raise
    raise RuntimeError(f"retry loop ended unexpectedly for {operation}")
