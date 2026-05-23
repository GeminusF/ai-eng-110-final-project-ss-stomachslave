import asyncio

import pytest

from ai import Ingredient, NutritionFacts
from ai.providers.base import ProviderError
from foodanalyzer.concurrency.pipeline import lookup_nutrition_parallel, sanitize_provider_error


class TrackingService:
    def __init__(self, fail: str | None = None) -> None:
        self.active = 0
        self.max_seen = 0
        self.fail = fail

    async def lookup_nutrition(self, name: str):
        self.active += 1
        self.max_seen = max(self.max_seen, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        if name == self.fail:
            raise ProviderError("provider unavailable")
        return (
            NutritionFacts(
                name=name,
                kcal_per_100g=10,
                protein_g_per_100g=1,
                carbs_g_per_100g=1,
                fat_g_per_100g=1,
                source="test",
            ),
            False,
        )


@pytest.mark.asyncio
async def test_pipeline_bounds_parallelism():
    ingredients = [
        Ingredient(name=f"item {i}", estimated_grams=100, confidence=0.9)
        for i in range(5)
    ]
    service = TrackingService()
    facts, warnings = await lookup_nutrition_parallel(
        ingredients,
        service,  # type: ignore[arg-type]
        max_concurrency=2,
    )
    assert len(facts) == 5
    assert warnings == []
    assert service.max_seen <= 2


@pytest.mark.asyncio
async def test_pipeline_handles_one_failed_lookup():
    ingredients = [
        Ingredient(name="rice", estimated_grams=100, confidence=0.9),
        Ingredient(name="bad", estimated_grams=100, confidence=0.9),
    ]
    service = TrackingService(fail="bad")
    facts, warnings = await lookup_nutrition_parallel(
        ingredients,
        service,  # type: ignore[arg-type]
        max_concurrency=2,
    )
    assert list(facts) == ["rice"]
    assert len(warnings) == 1


def test_pipeline_redacts_api_key_from_provider_errors():
    message = "GET /foods/search?query=rice&api_key=secret123 failed"

    assert sanitize_provider_error(message) == "GET /foods/search?query=rice&api_key=*** failed"