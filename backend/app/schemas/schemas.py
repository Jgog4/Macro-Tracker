"""
Pydantic v2 schemas — request bodies and response shapes for every endpoint.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Ingredient
# ─────────────────────────────────────────────────────────────────────────────

class IngredientBase(BaseModel):
    brand:             Optional[str]   = None
    name:              str
    serving_size_desc: Optional[str]   = None
    serving_size_g:    Optional[float] = None
    calories:          float           = 0.0
    protein_g:         float           = 0.0
    fat_g:             float           = 0.0
    sat_fat_g:         Optional[float] = None
    trans_fat_g:       Optional[float] = None
    carbs_g:           float           = 0.0
    fiber_g:           Optional[float] = None
    sugar_g:           Optional[float] = None
    sodium_mg:         Optional[float] = None
    cholesterol_mg:    Optional[float] = None


class IngredientCreate(IngredientBase):
    source:      str           = "custom"
    usda_fdc_id: Optional[int] = None


class IngredientUpdate(BaseModel):
    """Partial update — all fields optional."""
    brand:             Optional[str]   = None
    name:              Optional[str]   = None
    serving_size_desc: Optional[str]   = None
    serving_size_g:    Optional[float] = None
    calories:          Optional[float] = None
    protein_g:         Optional[float] = None
    fat_g:             Optional[float] = None
    sat_fat_g:         Optional[float] = None
    trans_fat_g:       Optional[float] = None
    carbs_g:           Optional[float] = None
    fiber_g:           Optional[float] = None
    sugar_g:           Optional[float] = None
    sodium_mg:         Optional[float] = None
    cholesterol_mg:    Optional[float] = None


class IngredientRead(IngredientBase):
    id:         str
    source:     str
    usda_fdc_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Recipe
# ─────────────────────────────────────────────────────────────────────────────

class RecipeIngredientCreate(BaseModel):
    ingredient_id: str
    quantity_g:    float = Field(..., gt=0, description="Grams of this ingredient in the recipe batch")


class RecipeIngredientRead(BaseModel):
    id:            str
    ingredient_id: str
    ingredient:    IngredientRead
    quantity_g:    float

    model_config = {"from_attributes": True}


class RecipeCreate(BaseModel):
    name:           str
    description:    Optional[str]   = None
    serving_size_g: Optional[float] = None
    ingredients:    list[RecipeIngredientCreate] = Field(..., min_length=1)


class RecipeRead(BaseModel):
    id:             str
    name:           str
    description:    Optional[str]   = None
    serving_size_g: Optional[float] = None
    total_weight_g: Optional[float] = None

    # Computed totals
    calories:       float
    protein_g:      float
    fat_g:          float
    carbs_g:        float
    sodium_mg:      float
    cholesterol_mg: float

    ingredients: list[RecipeIngredientRead] = []
    created_at:  datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Meal Log
# ─────────────────────────────────────────────────────────────────────────────

class MealLogItemCreate(BaseModel):
    ingredient_id: Optional[str]   = None
    recipe_id:     Optional[str]   = None
    quantity_g:    float           = Field(..., gt=0)

    model_config = {"json_schema_extra": {"examples": [
        {"ingredient_id": "<uuid>", "quantity_g": 113},
        {"recipe_id":     "<uuid>", "quantity_g": 495},
    ]}}


class MealLogCreate(BaseModel):
    """
    POST body to add food to a meal.
    If meal_number is omitted, the service auto-increments from today's count.
    If logged_at is omitted, the server uses the current timestamp.
    """
    log_date:    Optional[date]     = None   # defaults to today
    meal_number: Optional[int]      = None   # auto-assigned if omitted
    logged_at:   Optional[datetime] = None   # defaults to now()
    items:       list[MealLogItemCreate] = Field(..., min_length=1)


class MealLogItemUpdate(BaseModel):
    quantity_g: Optional[float] = None
    logged_at:  Optional[datetime] = None


class MealLogItemRead(BaseModel):
    id:            str
    ingredient_id: Optional[str] = None
    recipe_id:     Optional[str] = None
    display_name:  str
    quantity_g:    float

    calories:       float
    protein_g:      float
    fat_g:          float
    carbs_g:        float
    sodium_mg:      float
    cholesterol_mg: float

    logged_at: datetime

    model_config = {"from_attributes": True}


class MealLogRead(BaseModel):
    id:          str
    log_date:    date
    meal_number: int
    logged_at:   datetime

    total_calories:       float
    total_protein_g:      float
    total_fat_g:          float
    total_carbs_g:        float
    total_sodium_mg:      float
    total_cholesterol_mg: float

    items: list[MealLogItemRead] = []

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Daily Targets
# ─────────────────────────────────────────────────────────────────────────────

class DailyTargetCreate(BaseModel):
    target_date:    date
    calories:       float = 2000.0
    protein_g:      float = 150.0
    fat_g:          float = 70.0
    carbs_g:        float = 250.0
    sodium_mg:      float = 2300.0
    cholesterol_mg: float = 300.0


class DailyTargetRead(DailyTargetCreate):
    id:         str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard — Daily Summary
# ─────────────────────────────────────────────────────────────────────────────

class MacroStat(BaseModel):
    consumed:  float
    target:    float
    remaining: float
    pct:       float   # 0–100

class DailySummaryRead(BaseModel):
    log_date:    date
    energy:      MacroStat
    protein:     MacroStat
    fat:         MacroStat
    net_carbs:   MacroStat
    sodium:      MacroStat
    cholesterol: MacroStat
    meals:       list[MealLogRead] = []

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Decision Engine — "What should I eat?"
# ─────────────────────────────────────────────────────────────────────────────

class RemainingBudget(BaseModel):
    calories:  float
    protein_g: float
    fat_g:     float
    carbs_g:   float

class SuggestionRead(BaseModel):
    ingredient: IngredientRead
    fit_score:  float   = Field(description="0–1 closeness to remaining fat+protein budget")
    delta_protein_g: float
    delta_fat_g:     float

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Vision / OCR
# ─────────────────────────────────────────────────────────────────────────────

class VisionExtractResponse(BaseModel):
    """Structured macros returned by Claude after analysing an image."""
    name:             Optional[str]   = None
    serving_size:     Optional[str]   = None
    serving_size_g:   Optional[float] = None   # parsed grams from serving_size
    calories:         Optional[float] = None
    protein_g:        Optional[float] = None
    fat_g:            Optional[float] = None
    carbs_g:          Optional[float] = None
    sodium_mg:        Optional[float] = None
    cholesterol_mg:   Optional[float] = None
    confidence:       float           = Field(default=1.0, ge=0, le=1)
    raw_text:         Optional[str]   = None


# ─────────────────────────────────────────────────────────────────────────────
# USDA Search
# ─────────────────────────────────────────────────────────────────────────────

class USDASearchResult(BaseModel):
    fdc_id:         int
    description:    str
    brand_owner:    Optional[str] = None
    serving_size:   Optional[float] = None
    serving_unit:   Optional[str] = None
    calories:       Optional[float] = None
    protein_g:      Optional[float] = None
    fat_g:          Optional[float] = None
    carbs_g:        Optional[float] = None
    sodium_mg:      Optional[float] = None
    cholesterol_mg: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class ApiKeyRead(BaseModel):
    id:           str
    name:         str
    is_active:    bool
    created_at:   datetime
    last_used_at: Optional[datetime] = None
    # raw_key is only present on CREATE response
    raw_key:      Optional[str] = None

    model_config = {"from_attributes": True}
