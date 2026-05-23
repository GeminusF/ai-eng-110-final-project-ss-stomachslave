import pytest

from foodanalyzer.models import AnalysisResult, AnalysisStatus
from foodanalyzer.storage.repository import InMemoryAnalysisRepository


@pytest.mark.asyncio
async def test_memory_repository_save_get_list():
    repo = InMemoryAnalysisRepository()
    result = AnalysisResult(status=AnalysisStatus.unknown_meal, image_path="meal.png")

    saved = await repo.save(result)
    found = await repo.get(saved.id)
    recent = await repo.list_recent()

    assert found == saved
    assert recent == [saved]
    assert await repo.health() is True


@pytest.mark.asyncio
async def test_memory_repository_missing_id():
    repo = InMemoryAnalysisRepository()
    assert await repo.get("missing") is None
