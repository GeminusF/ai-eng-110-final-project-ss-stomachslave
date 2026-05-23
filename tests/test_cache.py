import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
from ai import NutritionFacts
from ai.providers.base import ProviderError

from foodanalyzer.services.nutrition_cache import (
    InMemoryNutritionCache,
    PostgresNutritionCache,
    normalize_ingredient_key,
)


def facts() -> NutritionFacts:
    return NutritionFacts(
        name="Rice",
        kcal_per_100g=130,
        protein_g_per_100g=2.7,
        carbs_g_per_100g=28,
        fat_g_per_100g=0.3,
        source="test",
    )


class FakeAcquire:
    def __init__(self, conn) -> None:
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self) -> None:
        self.conn = FakeConnection()

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConnection:
    def __init__(self) -> None:
        self.rows = {}
        self.schema_created = False
        self.schema_create_count = 0
        self.cleared = False

    async def execute(self, sql, *args):
        normalized_sql = " ".join(sql.split()).lower()
        if normalized_sql.startswith("create table"):
            await asyncio.sleep(0.01)
            self.schema_created = True
            self.schema_create_count += 1
        elif normalized_sql.startswith("insert into nutrition_cache"):
            key, ingredient_name, payload, expires_at = args
            self.rows[key] = {
                "ingredient_name": ingredient_name,
                "payload": payload,
                "expires_at": expires_at,
            }
        elif normalized_sql.startswith("delete from nutrition_cache where key"):
            key = args[0]
            row = self.rows.get(key)
            if row and row["expires_at"] <= datetime.now(timezone.utc):
                self.rows.pop(key, None)
        elif normalized_sql.startswith("delete from nutrition_cache"):
            self.rows.clear()
            self.cleared = True

    async def fetchrow(self, sql, *args):
        key = args[0]
        row = self.rows.get(key)
        if row is None or row["expires_at"] <= datetime.now(timezone.utc):
            return None
        return {"payload": row["payload"]}


def test_normalize_ingredient_key():
    assert normalize_ingredient_key(" White Rice (Cooked)! ") == "white rice cooked"


@pytest.mark.asyncio
async def test_memory_cache_hit():
    cache = InMemoryNutritionCache(ttl_seconds=60)

    await cache.set("Rice", facts())

    assert await cache.get("rice") is not None


@pytest.mark.asyncio
async def test_memory_cache_expiry():
    cache = InMemoryNutritionCache(ttl_seconds=0)

    await cache.set("Rice", facts())

    assert await cache.get("Rice") is None


@pytest.mark.asyncio
async def test_postgres_cache_set_then_get():
    pool = FakePool()
    cache = PostgresNutritionCache("postgresql://test", ttl_seconds=60)
    cache._pool = pool

    await cache.set("White Rice!", facts())
    cached = await cache.get("white rice")

    assert cached == facts()
    assert pool.conn.schema_created is True


@pytest.mark.asyncio
async def test_postgres_cache_expired_row_returns_none():
    pool = FakePool()
    cache = PostgresNutritionCache("postgresql://test", ttl_seconds=60)
    cache._pool = pool
    key = normalize_ingredient_key("Rice")
    pool.conn.rows[key] = {
        "ingredient_name": "Rice",
        "payload": json.dumps(facts().model_dump(mode="json")),
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    }

    assert await cache.get("Rice") is None
    assert key not in pool.conn.rows


@pytest.mark.asyncio
async def test_postgres_cache_clear():
    pool = FakePool()
    cache = PostgresNutritionCache("postgresql://test", ttl_seconds=60)
    cache._pool = pool

    await cache.set("Rice", facts())
    await cache.clear()

    assert pool.conn.rows == {}
    assert pool.conn.cleared is True


@pytest.mark.asyncio
async def test_postgres_cache_schema_creation_is_serialized():
    pool = FakePool()
    cache = PostgresNutritionCache("postgresql://test", ttl_seconds=60)
    cache._pool = pool

    await asyncio.gather(
        cache.get("rice"),
        cache.get("broccoli"),
        cache.set("egg", facts()),
    )

    assert pool.conn.schema_create_count == 1


@pytest.mark.asyncio
async def test_postgres_cache_reports_unavailable_database(monkeypatch):
    async def fake_create_pool(database_url):
        raise OSError("connection refused")

    monkeypatch.setitem(
        __import__("sys").modules,
        "asyncpg",
        SimpleNamespace(create_pool=fake_create_pool),
    )
    cache = PostgresNutritionCache("postgresql://test", ttl_seconds=60)

    with pytest.raises(ProviderError, match="PostgreSQL nutrition cache is unavailable"):
        await cache.get("Rice")