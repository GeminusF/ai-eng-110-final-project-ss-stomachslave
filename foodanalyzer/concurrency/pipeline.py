"""Bounded parallel nutrition lookup pipeline."""

from __future__ import annotations

import asyncio
import logging
import re

from ai import Ingredient, NutritionFacts
from ai.providers.base import ProviderError

from foodanalyzer.services.ai_service import AIService

logger = logging.getLogger(__name__)


def sanitize_provider_error(message: str) -> str:
    return re.sub(r"api_key=[^&\s)]+", "api_key=***", message)


async def lookup_nutrition_parallel(
    ingredients: list[Ingredient],
    ai_service: AIService,
    *,
    max_concurrency: int,
) -> tuple[dict[str, NutritionFacts], list[str]]:
    semaphore = asyncio.Semaphore(max_concurrency)
    facts_by_name: dict[str, NutritionFacts] = {}
    warnings: list[str] = []

    async def one(ingredient: Ingredient) -> None:
        async with semaphore:
            try:
                facts, _cached = await ai_service.lookup_nutrition(ingredient.name)
            except (ProviderError, OSError, TimeoutError, ValueError) as exc:
                msg = f"Nutrition lookup failed for {ingredient.name}: {sanitize_provider_error(str(exc))}"
                logger.warning("nutrition_lookup_failed", extra={"ingredient": ingredient.name})
                warnings.append(msg)
                return
            facts_by_name[ingredient.name] = facts

    await asyncio.gather(*(one(ingredient) for ingredient in ingredients))
    return facts_by_name, warnings