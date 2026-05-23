"""Wrapper around the provided `ai` package."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import ai
from ai import Ingredient, NutritionFacts, NutritionProvider

from foodanalyzer.services.nutrition_cache import InMemoryNutritionCache, NutritionCacheBackend
from foodanalyzer.services.retry import run_with_retries

logger = logging.getLogger(__name__)


class AIService:
    def __init__(
        self,
        *,
        vlm=None,
        nutrition_provider: NutritionProvider | None = None,
        cache: NutritionCacheBackend | None = None,
        retry_attempts: int = 3,
    ) -> None:
        self.vlm = vlm
        self._nutrition_provider = nutrition_provider
        self.cache = cache or InMemoryNutritionCache()
        self.retry_attempts = retry_attempts

    def _nutrition(self) -> NutritionProvider:
        if self._nutrition_provider is None:
            self._nutrition_provider = ai.get_nutrition_provider()
        return self._nutrition_provider

    async def identify_ingredients(self, image_path: str | Path) -> list[Ingredient]:
        logger.info("identify_ingredients_start", extra={"image_path": str(image_path)})

        async def call() -> list[Ingredient]:
            return await asyncio.to_thread(
                ai.identify_ingredients,
                str(image_path),
                vlm=self.vlm,
            )

        ingredients = await run_with_retries(
            "identify_ingredients",
            call,
            attempts=self.retry_attempts,
        )
        logger.info("identify_ingredients_done", extra={"count": len(ingredients)})
        return ingredients

    async def lookup_nutrition(self, ingredient_name: str) -> tuple[NutritionFacts, bool]:
        cached = await self.cache.get(ingredient_name)
        if cached is not None:
            logger.info("nutrition_cache_hit", extra={"ingredient": ingredient_name})
            return cached, True

        logger.info("nutrition_cache_miss", extra={"ingredient": ingredient_name})

        async def call() -> NutritionFacts:
            return await asyncio.to_thread(self._nutrition().lookup, ingredient_name)

        facts = await run_with_retries(
            "lookup_nutrition",
            call,
            attempts=self.retry_attempts,
        )
        await self.cache.set(ingredient_name, facts)
        return facts, False

    def compute_totals(
        self,
        ingredients: list[Ingredient],
        facts_by_name: dict[str, NutritionFacts],
    ):
        return ai.compute_totals(ingredients, facts_by_name)