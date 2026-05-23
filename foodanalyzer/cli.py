"""Command line interface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from ai import USDAProvider
from ai.providers.base import ProviderError

from foodanalyzer.config import Settings, get_settings
from foodanalyzer.core.analyzer import AnalyzerService
from foodanalyzer.logging_config import configure_logging
from foodanalyzer.models import AnalysisResult
from foodanalyzer.offline import OfflineNutritionProvider, OfflineVLM
from foodanalyzer.providers.openrouter import OpenRouterVLM
from foodanalyzer.services.ai_service import AIService
from foodanalyzer.services.nutrition_cache import InMemoryNutritionCache, PostgresNutritionCache
from foodanalyzer.storage.repository import InMemoryAnalysisRepository, PostgresAnalysisRepository
from foodanalyzer.utils.images import ImageValidationError, validate_image_path

app = typer.Typer(help="AI Food Analyzer")


def build_vlm(settings: Settings, *, offline: bool):
    if offline:
        return OfflineVLM()
    if settings.llm_provider.lower().strip() == "openrouter":
        return OpenRouterVLM(
            model=settings.llm_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            reasoning_enabled=settings.openrouter_reasoning_enabled,
            reasoning_exclude=settings.openrouter_reasoning_exclude,
        )
    return None


def build_nutrition_provider(settings: Settings, *, offline: bool):
    if offline:
        return OfflineNutritionProvider()

    provider = settings.nutrition_provider.lower().strip()
    if provider == "usda":
        return USDAProvider(api_key=settings.usda_api_key)

    raise ProviderError(
        f"Unknown NUTRITION_PROVIDER={provider!r}. Only 'usda' is supported by the app layer."
    )


def build_analyzer(settings: Settings, *, offline: bool) -> AnalyzerService:
    repository = InMemoryAnalysisRepository() if offline else PostgresAnalysisRepository(settings.database_url)
    cache = (
        InMemoryNutritionCache(settings.nutrition_cache_ttl_seconds)
        if offline
        else PostgresNutritionCache(settings.database_url, settings.nutrition_cache_ttl_seconds)
    )
    ai_service = AIService(
        vlm=build_vlm(settings, offline=offline),
        nutrition_provider=build_nutrition_provider(settings, offline=offline),
        cache=cache,
        retry_attempts=settings.retry_attempts,
    )
    return AnalyzerService(
        ai_service=ai_service,
        repository=repository,
        max_concurrency=settings.max_concurrency,
    )


@app.command()
def analyze(
    image_path: Path,
    offline: bool = typer.Option(False, "--offline", help="Use fake providers, no keys or network."),
    json_output: bool = typer.Option(False, "--json", help="Print structured JSON."),
    save: bool = typer.Option(True, "--save/--no-save", help="Persist the analysis result."),
) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        valid_path = validate_image_path(image_path, settings.max_image_bytes)
    except ImageValidationError as exc:
        typer.echo(f"Invalid image: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    analyzer = build_analyzer(settings, offline=offline or settings.offline_mode)
    result = asyncio.run(analyzer.analyze(valid_path, save=save))
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
        return
    typer.echo(render_result(result))


@app.command()
def history(limit: int = typer.Option(10, min=1, max=100)) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    repository = PostgresAnalysisRepository(settings.database_url)

    async def run() -> None:
        records = await repository.list_recent(limit)
        if not records:
            typer.echo("No analyses found.")
            return
        for record in records:
            typer.echo(f"{record.id}  {record.created_at.isoformat()}  {record.status}")

    asyncio.run(run())


def render_result(result: AnalysisResult) -> str:
    if result.status == "unknown_meal" or not result.ingredients:
        return "No meal was recognized in this image."

    headers = ("ingredient", "g", "kcal", "protein", "carbs", "fat")
    rows = [
        (
            item.name,
            f"{item.grams:.0f}",
            f"{item.nutrition.kcal:.0f}",
            f"{item.nutrition.protein_g:.1f}",
            f"{item.nutrition.carbs_g:.1f}",
            f"{item.nutrition.fat_g:.1f}",
        )
        for item in result.ingredients
    ]
    rows.append(
        (
            "TOTAL",
            f"{sum(item.grams for item in result.ingredients):.0f}",
            f"{result.totals.kcal:.0f}",
            f"{result.totals.protein_g:.1f}",
            f"{result.totals.carbs_g:.1f}",
            f"{result.totals.fat_g:.1f}",
        )
    )
    widths = [max(len(headers[i]), max(len(row[i]) for row in rows)) for i in range(len(headers))]

    def fmt(row: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[i]) for i, value in enumerate(row))

    line = "-" * (sum(widths) + 2 * (len(widths) - 1))
    body = [fmt(headers), line]
    body.extend(fmt(row) for row in rows[:-1])
    body.extend([line, fmt(rows[-1])])
    if result.warnings:
        body.append("")
        body.extend(f"warning: {warning}" for warning in result.warnings)
    return "\n".join(body)