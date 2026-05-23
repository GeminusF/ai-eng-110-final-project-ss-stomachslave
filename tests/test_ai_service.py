import pytest

from tests.conftest import FakeNutrition, FakeVLM
from foodanalyzer.offline import OfflineNutritionProvider, OfflineVLM
from foodanalyzer.services.ai_service import AIService
from foodanalyzer.services.nutrition_cache import InMemoryNutritionCache


@pytest.mark.asyncio
async def test_ai_service_identifies_ingredients(sample_image):
    service = AIService(
        vlm=FakeVLM(),
        nutrition_provider=FakeNutrition(),
        cache=InMemoryNutritionCache(),
        retry_attempts=1,
    )
    ingredients = await service.identify_ingredients(sample_image)
    assert [ingredient.name for ingredient in ingredients] == [
        "white rice (cooked)",
        "grilled chicken breast",
        "broccoli",
    ]


@pytest.mark.asyncio
async def test_ai_service_unknown_meal_returns_empty_list(sample_image):
    service = AIService(
        vlm=FakeVLM({"meal_recognized": False, "ingredients": []}),
        nutrition_provider=FakeNutrition(),
        retry_attempts=1,
    )
    assert await service.identify_ingredients(sample_image) == []


@pytest.mark.asyncio
async def test_lookup_nutrition_uses_cache():
    cache = InMemoryNutritionCache()
    service = AIService(
        vlm=OfflineVLM(),
        nutrition_provider=OfflineNutritionProvider(),
        cache=cache,
        retry_attempts=1,
    )
    first, first_cached = await service.lookup_nutrition("broccoli")
    second, second_cached = await service.lookup_nutrition("broccoli")
    assert first == second
    assert first_cached is False
    assert second_cached is True