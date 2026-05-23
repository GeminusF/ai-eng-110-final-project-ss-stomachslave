"""TTL caches for nutrition lookups."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
import time
from typing import Protocol

from ai import NutritionFacts
from ai.providers.base import ProviderError


def normalize_ingredient_key(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


class NutritionCacheBackend(Protocol):
    async def get(self, ingredient_name: str) -> NutritionFacts | None: ...
    async def set(self, ingredient_name: str, facts: NutritionFacts) -> None: ...
    async def clear(self) -> None: ...


@dataclass
class CacheEntry:
    facts: NutritionFacts
    expires_at: float


class InMemoryNutritionCache:
    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, CacheEntry] = {}

    async def get(self, ingredient_name: str) -> NutritionFacts | None:
        key = normalize_ingredient_key(ingredient_name)
        entry = self._items.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.time():
            self._items.pop(key, None)
            return None
        return entry.facts

    async def set(self, ingredient_name: str, facts: NutritionFacts) -> None:
        key = normalize_ingredient_key(ingredient_name)
        self._items[key] = CacheEntry(
            facts=facts,
            expires_at=time.time() + self.ttl_seconds,
        )

    async def clear(self) -> None:
        self._items.clear()


class PostgresNutritionCache:
    def __init__(self, database_url: str, ttl_seconds: int = 86400) -> None:
        self.database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        self.ttl_seconds = ttl_seconds
        self._pool = None
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def _get_pool(self):
        if self._pool is None:
            try:
                import asyncpg
            except ImportError as exc:
                raise ProviderError("asyncpg is required for PostgreSQL nutrition cache") from exc
            try:
                self._pool = await asyncpg.create_pool(self.database_url)
            except Exception as exc:
                raise ProviderError(
                    "PostgreSQL nutrition cache is unavailable. "
                    "Start PostgreSQL or use Offline demo."
                ) from exc
        return self._pool

    async def create_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)
            self._schema_ready = True

    async def get(self, ingredient_name: str) -> NutritionFacts | None:
        key = normalize_ingredient_key(ingredient_name)
        await self.create_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select payload
                from nutrition_cache
                where key = $1 and expires_at > now()
                """,
                key,
            )
            if row is None:
                await conn.execute(
                    "delete from nutrition_cache where key = $1 and expires_at <= now()",
                    key,
                )
                return None
        return _facts_from_payload(row["payload"])

    async def set(self, ingredient_name: str, facts: NutritionFacts) -> None:
        key = normalize_ingredient_key(ingredient_name)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        payload = json.dumps(facts.model_dump(mode="json"))
        await self.create_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                insert into nutrition_cache (key, ingredient_name, payload, expires_at, updated_at)
                values ($1, $2, $3::jsonb, $4, now())
                on conflict (key) do update set
                    ingredient_name = excluded.ingredient_name,
                    payload = excluded.payload,
                    expires_at = excluded.expires_at,
                    updated_at = now()
                """,
                key,
                ingredient_name,
                payload,
                expires_at,
            )

    async def clear(self) -> None:
        await self.create_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("delete from nutrition_cache")


def _facts_from_payload(payload) -> NutritionFacts:
    if isinstance(payload, str):
        payload = json.loads(payload)
    return NutritionFacts.model_validate(payload)


SCHEMA_SQL = """
create table if not exists nutrition_cache (
    key text primary key,
    ingredient_name text not null,
    payload jsonb not null,
    expires_at timestamptz not null,
    updated_at timestamptz not null
);
"""


NutritionCache = InMemoryNutritionCache