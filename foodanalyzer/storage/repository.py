"""Repositories for analysis history."""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Protocol

from foodanalyzer.models import AnalysisRecord, AnalysisResult


class AnalysisRepository(Protocol):
    async def save(self, result: AnalysisResult) -> AnalysisRecord: ...
    async def list_recent(self, limit: int = 10) -> list[AnalysisRecord]: ...
    async def get(self, analysis_id: str) -> AnalysisRecord | None: ...
    async def health(self) -> bool: ...


class InMemoryAnalysisRepository:
    def __init__(self) -> None:
        self._items: OrderedDict[str, AnalysisRecord] = OrderedDict()

    async def save(self, result: AnalysisResult) -> AnalysisRecord:
        record = AnalysisRecord.model_validate(result.model_dump())
        self._items[record.id] = record
        return record

    async def list_recent(self, limit: int = 10) -> list[AnalysisRecord]:
        return list(reversed(list(self._items.values())))[:limit]

    async def get(self, analysis_id: str) -> AnalysisRecord | None:
        return self._items.get(analysis_id)

    async def health(self) -> bool:
        return True


class PostgresAnalysisRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            try:
                import asyncpg
            except ImportError as exc:
                raise RuntimeError("asyncpg is required for PostgreSQL storage") from exc
            self._pool = await asyncpg.create_pool(self.database_url)
        return self._pool

    async def create_schema(self) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

    async def save(self, result: AnalysisResult) -> AnalysisRecord:
        await self.create_schema()
        record = AnalysisRecord.model_validate(result.model_dump())
        pool = await self._get_pool()
        payload = json.dumps(record.model_dump(mode="json"))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                insert into analyses (id, created_at, image_path, status, payload)
                values ($1, $2, $3, $4, $5::jsonb)
                on conflict (id) do update set payload = excluded.payload
                """,
                record.id,
                record.created_at,
                record.image_path,
                record.status.value,
                payload,
            )
        return record

    async def list_recent(self, limit: int = 10) -> list[AnalysisRecord]:
        await self.create_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "select payload from analyses order by created_at desc limit $1",
                limit,
            )
        return [AnalysisRecord.model_validate(json.loads(row["payload"])) for row in rows]

    async def get(self, analysis_id: str) -> AnalysisRecord | None:
        await self.create_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("select payload from analyses where id = $1", analysis_id)
        if row is None:
            return None
        return AnalysisRecord.model_validate(json.loads(row["payload"]))

    async def health(self) -> bool:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute("select 1")
            return True
        except Exception:
            return False


SCHEMA_SQL = """
create table if not exists analyses (
    id text primary key,
    created_at timestamptz not null,
    image_path text not null,
    status text not null,
    payload jsonb not null
);
"""
