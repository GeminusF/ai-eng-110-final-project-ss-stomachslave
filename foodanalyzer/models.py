"""Application models for the Food Analyzer SE layer."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ai import Nutrition


class AnalysisStatus(str, Enum):
    completed = "completed"
    unknown_meal = "unknown_meal"
    partial = "partial"
    failed = "failed"


class NutritionTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0

    @classmethod
    def from_ai(cls, nutrition: Nutrition) -> "NutritionTotals":
        return cls(
            kcal=round(nutrition.kcal, 2),
            protein_g=round(nutrition.protein_g, 2),
            carbs_g=round(nutrition.carbs_g, 2),
            fat_g=round(nutrition.fat_g, 2),
        )


class IngredientResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    grams: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    nutrition: NutritionTotals
    source: str | None = None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    status: AnalysisStatus
    image_path: str
    ingredients: list[IngredientResult] = Field(default_factory=list)
    totals: NutritionTotals = Field(default_factory=NutritionTotals)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisRecord(AnalysisResult):
    pass


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str
