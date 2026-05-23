"""Offline providers for no-key demos and tests."""

from __future__ import annotations

import json
from pathlib import Path

from ai import NutritionFacts, NutritionProvider
from ai.providers.base import ProviderError, VLMProvider


class OfflineVLM(VLMProvider):
    KNOWN = {
        "rice": ("white rice (cooked)", 180.0),
        "chicken": ("grilled chicken breast", 150.0),
        "broccoli": ("broccoli", 80.0),
        "salmon": ("salmon, baked", 140.0),
        "potato": ("baked potato", 200.0),
        "egg": ("boiled egg", 50.0),
        "salad": ("mixed green salad", 100.0),
        "pasta": ("pasta, cooked", 220.0),
        "tomato": ("tomato, raw", 70.0),
        "cheese": ("cheddar cheese", 30.0),
        "avocado": ("avocado", 100.0),
        "bread": ("white bread", 60.0),
    }

    def describe(self, image_path: str, prompt: str, *, json_schema=None) -> str:
        stem = Path(image_path).stem.lower()
        ingredients = [
            {
                "name": name,
                "estimated_grams": grams,
                "confidence": 0.85,
            }
            for keyword, (name, grams) in self.KNOWN.items()
            if keyword in stem
        ]
        if not ingredients:
            return json.dumps({"meal_recognized": False, "ingredients": []})
        return json.dumps({"meal_recognized": True, "ingredients": ingredients})


def _facts(name: str, kcal: float, protein: float, carbs: float, fat: float) -> NutritionFacts:
    return NutritionFacts(
        name=name,
        kcal_per_100g=kcal,
        protein_g_per_100g=protein,
        carbs_g_per_100g=carbs,
        fat_g_per_100g=fat,
        source="offline",
    )


class OfflineNutritionProvider(NutritionProvider):
    DB = {
        "white rice (cooked)": _facts("Rice, white, cooked", 130, 2.7, 28, 0.3),
        "grilled chicken breast": _facts("Chicken breast, grilled", 165, 31, 0, 3.6),
        "broccoli": _facts("Broccoli, raw", 34, 2.8, 7, 0.4),
        "salmon, baked": _facts("Salmon, baked", 206, 22, 0, 13),
        "baked potato": _facts("Potato, baked", 93, 2.5, 21, 0.1),
        "boiled egg": _facts("Egg, boiled", 155, 13, 1.1, 11),
        "mixed green salad": _facts("Lettuce, mixed greens", 15, 1.4, 2.9, 0.2),
        "pasta, cooked": _facts("Pasta, cooked", 158, 5.8, 31, 0.9),
        "tomato, raw": _facts("Tomato, raw", 18, 0.9, 3.9, 0.2),
        "cheddar cheese": _facts("Cheese, cheddar", 403, 25, 1.3, 33),
        "avocado": _facts("Avocado, raw", 160, 2, 9, 15),
        "white bread": _facts("Bread, white", 265, 9, 49, 3.2),
    }

    def lookup(self, ingredient_name: str) -> NutritionFacts:
        try:
            return self.DB[ingredient_name]
        except KeyError as exc:
            raise ProviderError(f"unknown ingredient: {ingredient_name!r}") from exc
