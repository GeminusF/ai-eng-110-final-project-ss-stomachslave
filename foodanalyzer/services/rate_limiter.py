"""Small async semaphore wrapper for bounded external calls."""

from __future__ import annotations

import asyncio


class RateLimiter:
    def __init__(self, max_concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self) -> "RateLimiter":
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._semaphore.release()
