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

    # Core macros
    calories:       float           = 0.0
    protein_g:      float           = 0.0
    fat_g:          float           = 0.0
    sat_fat_g:      Optional[float] = None
    trans_fat_g:    Optional[float] = None
    carbs_g:        float           = 0.0
    fiber_g:        Optional[float] = None
    sugar_g:        Optional[float] = None
    added_sugar_g:  Optional[float] = None
    sodium_mg:      Optional[float] = None
    cholesterol_mg: Optional[float] = None
    potassium_mg:   Optional[float] = None

    # Vitamins
    vitamin_a_mcg:          Optional[float] = None
    vitamin_c_mg:           Optional[float] = None
    vitamin_d_mcg:          Optional[float] = None
    vitamin_e_mg:           Optional[float] = None
    vitamin_k_mcg:          Optional[float] = None
    thiamine_mg:            Optional[float] = None   # B1
    riboflavin_mg:          Optional[float] = None   # B2
    niacin_mg:              Optional[float] = None   # B3
    pantothenic_acid_mg:    Optional[float] = None   # B5
    pyridoxine_mg:          Optional[float] = None   # B6
    cobalamin_mcg:          Optional[float] = None   # B12
    biotin_mcg:             Optional[float] = None
    folate_mcg:             Optional[float] = None
    choline_mg:             Optional[float] = None
    retinol_mcg:            Optional[float] = None
    alpha_carotene_mcg:     Optional[float] = None
    beta_carotene_mcg:      Optional[float] = None
    beta_cryptoxanthin_mcg: Optional[float] = None
    lutein_zeaxanthin_mcg:  Optional[float] = None
    lycopene_mcg:           Optional[float] = None
    beta_tocopherol_mg:     Optional[float] = None
    delta_tocopherol_mg:    Optional[float] = None
    gamma_tocopherol_mg:    Optional[float] = None

    # Minerals
    calcium_mg:     Optional[float] = None
    iron_mg:        Optional[float] = None
    magnesium_mg:   Optional[float] = None
    phosphorus_mg:  Optional[float] = None
    zinc_mg:        Optional[float] = None
    copper_mg:      Optional[float] = None
    manganese_mg:   Optional[float] = None
    selenium_mcg:   Optional[float] = None
    chromium_mcg:   Optional[float] = None
    iodine_mcg:     Optional[float] = None
    molybdenum_mcg: Optional[float] = None
    fluoride_mg:    Optional[float] = None

    # Amino acids
    alanine_g:       Optional[float] = None
    arginine_g:      Optional[float] = None
    aspartic_acid_g: Optional[float] = None
    cystine_g:       Optional[float] = None
    glutamic_acid_g: Optional[float] = None
    glycine_g:       Optional[float] = None
    histidine_g:     Optional[float] = None
    hydroxyproline_g:Optional[float] = None
    isoleucine_g:    Optional[float] = None
    leucine_g:       Optional[float] = None
    lysine_g:        Optional[float] = None
    methionine_g:    Optional[float] = None
    phenylalanine_g: Optional[float] = None
    proline_g:       Optional[float] = None
    serine_g:        Optional[float] = None
    threonine_g:     Optional[float] = None
    tryptophan_g:    Optional[float] = None
    tyrosine_g:      Optional[float] = None
    valine_g:        Optional[float] = None

    # Fatty acids
    monounsaturated_fat_g: Optional[float] = None
    polyunsaturated_fat_g: Optional[float] = None
    omega3_ala_g:          Optional[float] = None
    omega3_dha_g:          Optional[float] = None
    omega3_epa_g:          Optional[float] = None
    omega6_aa_g:           Optional[float] = None
    omega6_la_g:           Optional[float] = None
    phytosterol_mg:        Optional[float] = None

    # Carb details & other
    soluble_fiber_g:        Optional[float] = None
    insoluble_fiber_g:      Optional[float] = None
    fructose_g:             Optional[float] = None
    galactose_g:            Optional[float] = None
    glucose_g:              Optional[float] = None
    lactose_g:              Optional[float] = None
    maltose_g:              Optional[float] = None
    sucrose_g:              Optional[float] = None
    oxalate_mg:             Optional[float] = None
    phytate_mg:             Optional[float] = None
    caffeine_mg:            Optional[float] = None
    water_g:                Optional[float] = None
    ash_g:                  Optional[float] = None
    alcohol_g:              Optional[float] = None
    beta_hydroxybutyrate_g: Optional[float] = None


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
    added_sugar_g:     Optional[float] = None
    sodium_mg:         Optional[float] = None
    cholesterol_mg:    Optional[float] = None
    potassium_mg:      Optional[float] = None
    # Vitamins
    vitamin_a_mcg:          Optional[float] = None
    vitamin_c_mg:           Optional[float] = None
    vitamin_d_mcg:          Optional[float] = None
    vitamin_e_mg:           Optional[float] = None
    vitamin_k_mcg:          Optional[float] = None
    thiamine_mg:            Optional[float] = None
    riboflavin_mg:          Optional[float] = None
    niacin_mg:              Optional[float] = None
    pantothenic_acid_mg:    Optional[float] = None
    pyridoxine_mg:          Optional[float] = None
    cobalamin_mcg:          Optional[float] = None
    biotin_mcg:             Optional[float] = None
    folate_mcg:             Optional[float] = None
    choline_mg:             Optional[float] = None
    # Minerals
    calcium_mg:     Optional[float] = None
    iron_mg:        Optional[float] = None
    magnesium_mg:   Optional[float] = None
    phosphorus_mg:  Optional[float] = None
    zinc_mg:        Optional[float] = None
    copper_mg:      Optional[float] = None
    manganese_mg:   Optional[float] = None
    selenium_mcg:   Optional[float] = None


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


class RecipeUpdate(BaseModel):
    name:           Optional[str]   = None
    description:    Optional[str]   = None
    serving_size_g: Optional[float] = None
    ingredients:    Optional[list[RecipeIngredientCreate]] = None


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


class MealCopyRequest(BaseModel):
    target_date:        date
    target_meal_number: int
    logged_at:          Optional[datetime] = None   # time for copied items; defaults to now()


class MealLogItemComponentRead(BaseModel):
    """Sub-ingredient snapshot from a logged recipe."""
    id:             str
    ingredient_id:  Optional[str] = None
    ingredient_name: str
    quantity_g:     float

    model_config = {"from_attributes": True}


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

    # Non-empty only when recipe_id is set
    components: list[MealLogItemComponentRead] = []

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
# Micronutrient Summary
# ─────────────────────────────────────────────────────────────────────────────

class MicronutrientTotals(BaseModel):
    """All micronutrient totals for a given period. None = no data tracked."""

    # Vitamins
    vitamin_a_mcg:          Optional[float] = None
    vitamin_c_mg:           Optional[float] = None
    vitamin_d_mcg:          Optional[float] = None
    vitamin_e_mg:           Optional[float] = None
    vitamin_k_mcg:          Optional[float] = None
    thiamine_mg:            Optional[float] = None
    riboflavin_mg:          Optional[float] = None
    niacin_mg:              Optional[float] = None
    pantothenic_acid_mg:    Optional[float] = None
    pyridoxine_mg:          Optional[float] = None
    cobalamin_mcg:          Optional[float] = None
    biotin_mcg:             Optional[float] = None
    folate_mcg:             Optional[float] = None
    choline_mg:             Optional[float] = None
    retinol_mcg:            Optional[float] = None
    alpha_carotene_mcg:     Optional[float] = None
    beta_carotene_mcg:      Optional[float] = None
    beta_cryptoxanthin_mcg: Optional[float] = None
    lutein_zeaxanthin_mcg:  Optional[float] = None
    lycopene_mcg:           Optional[float] = None
    beta_tocopherol_mg:     Optional[float] = None
    delta_tocopherol_mg:    Optional[float] = None
    gamma_tocopherol_mg:    Optional[float] = None

    # Minerals
    calcium_mg:     Optional[float] = None
    iron_mg:        Optional[float] = None
    magnesium_mg:   Optional[float] = None
    phosphorus_mg:  Optional[float] = None
    zinc_mg:        Optional[float] = None
    copper_mg:      Optional[float] = None
    manganese_mg:   Optional[float] = None
    selenium_mcg:   Optional[float] = None
    chromium_mcg:   Optional[float] = None
    iodine_mcg:     Optional[float] = None
    molybdenum_mcg: Optional[float] = None
    fluoride_mg:    Optional[float] = None

    # Amino acids
    alanine_g:       Optional[float] = None
    arginine_g:      Optional[float] = None
    aspartic_acid_g: Optional[float] = None
    cystine_g:       Optional[float] = None
    glutamic_acid_g: Optional[float] = None
    glycine_g:       Optional[float] = None
    histidine_g:     Optional[float] = None
    hydroxyproline_g:Optional[float] = None
    isoleucine_g:    Optional[float] = None
    leucine_g:       Optional[float] = None
    lysine_g:        Optional[float] = None
    methionine_g:    Optional[float] = None
    phenylalanine_g: Optional[float] = None
    proline_g:       Optional[float] = None
    serine_g:        Optional[float] = None
    threonine_g:     Optional[float] = None
    tryptophan_g:    Optional[float] = None
    tyrosine_g:      Optional[float] = None
    valine_g:        Optional[float] = None

    # Fatty acids
    monounsaturated_fat_g: Optional[float] = None
    polyunsaturated_fat_g: Optional[float] = None
    omega3_ala_g:          Optional[float] = None
    omega3_dha_g:          Optional[float] = None
    omega3_epa_g:          Optional[float] = None
    omega6_aa_g:           Optional[float] = None
    omega6_la_g:           Optional[float] = None
    phytosterol_mg:        Optional[float] = None

    # Carb details & other
    soluble_fiber_g:        Optional[float] = None
    insoluble_fiber_g:      Optional[float] = None
    fructose_g:             Optional[float] = None
    galactose_g:            Optional[float] = None
    glucose_g:              Optional[float] = None
    lactose_g:              Optional[float] = None
    maltose_g:              Optional[float] = None
    sucrose_g:              Optional[float] = None
    oxalate_mg:             Optional[float] = None
    phytate_mg:             Optional[float] = None
    caffeine_mg:            Optional[float] = None
    water_g:                Optional[float] = None
    ash_g:                  Optional[float] = None
    alcohol_g:              Optional[float] = None
    beta_hydroxybutyrate_g: Optional[float] = None


class MicronutrientSummaryRead(BaseModel):
    """Micronutrient totals + per-day averages for a date range."""
    start_date:    date
    end_date:      date
    days_with_data: int
    totals:        MicronutrientTotals   # sum over the whole period
    daily_avg:     MicronutrientTotals   # totals / days_with_data (or None)


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
    """Structured nutrition data returned by Claude after analysing an image."""
    name:             Optional[str]   = None
    serving_size:     Optional[str]   = None
    serving_size_g:   Optional[float] = None
    # Macros
    calories:         Optional[float] = None
    protein_g:        Optional[float] = None
    fat_g:            Optional[float] = None
    sat_fat_g:        Optional[float] = None
    trans_fat_g:      Optional[float] = None
    carbs_g:          Optional[float] = None
    fiber_g:          Optional[float] = None
    sugar_g:          Optional[float] = None
    added_sugar_g:    Optional[float] = None
    # Standard label minerals / electrolytes
    sodium_mg:        Optional[float] = None
    cholesterol_mg:   Optional[float] = None
    potassium_mg:     Optional[float] = None
    calcium_mg:       Optional[float] = None
    iron_mg:          Optional[float] = None
    vitamin_d_mcg:    Optional[float] = None
    # Extended vitamins (visible on some labels)
    vitamin_a_mcg:    Optional[float] = None
    vitamin_c_mg:     Optional[float] = None
    vitamin_e_mg:     Optional[float] = None
    vitamin_k_mcg:    Optional[float] = None
    thiamine_mg:      Optional[float] = None
    riboflavin_mg:    Optional[float] = None
    niacin_mg:        Optional[float] = None
    folate_mcg:       Optional[float] = None
    cobalamin_mcg:    Optional[float] = None
    # Extended minerals (visible on some labels)
    magnesium_mg:     Optional[float] = None
    zinc_mg:          Optional[float] = None
    phosphorus_mg:    Optional[float] = None
    # Fatty acids (common on some labels)
    monounsaturated_fat_g: Optional[float] = None
    polyunsaturated_fat_g: Optional[float] = None
    omega3_ala_g:     Optional[float] = None
    omega3_dha_g:     Optional[float] = None
    omega3_epa_g:     Optional[float] = None
    # Carb details
    soluble_fiber_g:  Optional[float] = None
    insoluble_fiber_g:Optional[float] = None
    # Other
    caffeine_mg:      Optional[float] = None
    alcohol_g:        Optional[float] = None
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
