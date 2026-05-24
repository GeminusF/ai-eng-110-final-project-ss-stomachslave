"""Compare sequential vs concurrent nutrition lookup in offline mode."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from foodanalyzer.offline import OfflineNutritionProvider, OfflineVLM
from foodanalyzer.services.ai_service import AIService
from foodanalyzer.services.nutrition_cache import InMemoryNutritionCache
from foodanalyzer.concurrency.pipeline import lookup_nutrition_parallel


async def main(image: Path) -> None:
    service = AIService(
        vlm=OfflineVLM(),
        nutrition_provider=OfflineNutritionProvider(),
        cache=InMemoryNutritionCache(ttl_seconds=1),
        retry_attempts=1,
    )
    ingredients = await service.identify_ingredients(image)

    start = time.perf_counter()
    for ingredient in ingredients:
        await service.lookup_nutrition(ingredient.name)
    sequential = time.perf_counter() - start

    await service.cache.clear()
    start = time.perf_counter()
    await lookup_nutrition_parallel(ingredients, service, max_concurrency=10)
    concurrent = time.perf_counter() - start

    print("mode,ingredients,seconds")
    print(f"sequential,{len(ingredients)},{sequential:.4f}")
    print(f"concurrent,{len(ingredients)},{concurrent:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=Path("data/rice_chicken_broccoli.png"))
    args = parser.parse_args()
    asyncio.run(main(args.image))
