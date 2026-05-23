"""Meal analysis orchestration."""

from __future__ import annotations

from pathlib import Path

from ai import NutritionFacts

from foodanalyzer.concurrency.pipeline import lookup_nutrition_parallel
from foodanalyzer.models import AnalysisRecord, AnalysisResult, AnalysisStatus, IngredientResult, NutritionTotals
from foodanalyzer.services.ai_service import AIService
from foodanalyzer.storage.repository import AnalysisRepository


class AnalyzerService:
    def __init__(
        self,
        *,
        ai_service: AIService,
        repository: AnalysisRepository,
        max_concurrency: int,
    ) -> None:
        self.ai_service = ai_service
        self.repository = repository
        self.max_concurrency = max_concurrency

    async def analyze(self, image_path: str | Path, *, save: bool = True) -> AnalysisResult:
        image_text = str(image_path)
        ingredients = await self.ai_service.identify_ingredients(image_text)
        if not ingredients:
            result = AnalysisResult(
                status=AnalysisStatus.unknown_meal,
                image_path=image_text,
                warnings=["No meal was recognized in the image."],
            )
            return await self._maybe_save(result, save)

        facts_by_name, warnings = await lookup_nutrition_parallel(
            ingredients,
            self.ai_service,
            max_concurrency=self.max_concurrency,
        )
        if not facts_by_name:
            result = AnalysisResult(
                status=AnalysisStatus.failed,
                image_path=image_text,
                warnings=warnings,
                error_message="No nutrition facts could be fetched.",
            )
            return await self._maybe_save(result, save)

        totals = self.ai_service.compute_totals(ingredients, facts_by_name)
        rows = [
            self._ingredient_result(ingredient, facts_by_name[ingredient.name])
            for ingredient in ingredients
            if ingredient.name in facts_by_name
        ]
        status = AnalysisStatus.completed if len(rows) == len(ingredients) else AnalysisStatus.partial
        result = AnalysisResult(
            status=status,
            image_path=image_text,
            ingredients=rows,
            totals=NutritionTotals.from_ai(totals),
            warnings=warnings,
        )
        return await self._maybe_save(result, save)

    async def _maybe_save(self, result: AnalysisResult, save: bool) -> AnalysisResult:
        if not save:
            return result
        record: AnalysisRecord = await self.repository.save(result)
        return record

    @staticmethod
    def _ingredient_result(ingredient, facts: NutritionFacts) -> IngredientResult:
        return IngredientResult(
            name=ingredient.name,
            grams=ingredient.estimated_grams,
            confidence=ingredient.confidence,
            nutrition=NutritionTotals.from_ai(facts.for_grams(ingredient.estimated_grams)),
            source=facts.source,
        )
