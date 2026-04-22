"""
SQLAlchemy ORM models for the Macro Tracker app.

All tables are prefixed with mt_ to avoid conflicts with other apps
sharing the same Railway PostgreSQL instance.

Table overview
──────────────
mt_users                       – single-user profile
mt_daily_targets               – per-day macro goals
mt_ingredients                 – unified food database (USDA + restaurant + custom)
mt_recipes                     – custom multi-ingredient blends (e.g. "Turkey & Rice")
mt_recipe_ingredients          – junction: which ingredients in each recipe and at what qty
mt_meal_logs                   – one row per meal per day  (Meal 1, Meal 2, …)
mt_meal_log_items              – individual line items inside a meal (ingredient OR recipe)
mt_meal_log_item_components    – sub-ingredient snapshot when a recipe is logged
mt_api_keys                    – hashed keys for external tool access (Mac dashboard, etc.)
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "mt_users"

    id:         Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email:      Mapped[str]      = mapped_column(String(255), unique=True, nullable=False)
    name:       Mapped[str]      = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    targets:   Mapped[list["DailyTarget"]] = relationship("DailyTarget", back_populates="user", cascade="all, delete-orphan")
    meal_logs: Mapped[list["MealLog"]]     = relationship("MealLog",     back_populates="user", cascade="all, delete-orphan")
    api_keys:  Mapped[list["ApiKey"]]      = relationship("ApiKey",      back_populates="user", cascade="all, delete-orphan")


class DailyTarget(Base):
    __tablename__ = "mt_daily_targets"
    __table_args__ = (UniqueConstraint("user_id", "target_date", name="uq_mt_user_date_target"),)

    id:             Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:        Mapped[str]   = mapped_column(ForeignKey("mt_users.id", ondelete="CASCADE"), nullable=False)
    target_date:    Mapped[date]  = mapped_column(Date, nullable=False)

    calories:       Mapped[float] = mapped_column(Float, default=2000.0)
    protein_g:      Mapped[float] = mapped_column(Float, default=150.0)
    fat_g:          Mapped[float] = mapped_column(Float, default=70.0)
    carbs_g:        Mapped[float] = mapped_column(Float, default=250.0)
    sodium_mg:      Mapped[float] = mapped_column(Float, default=2300.0)
    cholesterol_mg: Mapped[float] = mapped_column(Float, default=300.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="targets")


class Ingredient(Base):
    __tablename__ = "mt_ingredients"

    id:     Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="custom")
    # source values: "usda" | "restaurant" | "custom"

    brand:             Mapped[str | None]   = mapped_column(String(255))
    name:              Mapped[str]          = mapped_column(String(500), nullable=False)
    serving_size_desc: Mapped[str | None]   = mapped_column(String(100))
    serving_size_g:    Mapped[float | None] = mapped_column(Float)

    # ── Core macros ──────────────────────────────────────────────────────────
    calories:       Mapped[float]        = mapped_column(Float, default=0.0)
    protein_g:      Mapped[float]        = mapped_column(Float, default=0.0)
    fat_g:          Mapped[float]        = mapped_column(Float, default=0.0)
    sat_fat_g:      Mapped[float | None] = mapped_column(Float)
    trans_fat_g:    Mapped[float | None] = mapped_column(Float)
    carbs_g:        Mapped[float]        = mapped_column(Float, default=0.0)
    fiber_g:        Mapped[float | None] = mapped_column(Float)
    sugar_g:        Mapped[float | None] = mapped_column(Float)
    added_sugar_g:  Mapped[float | None] = mapped_column(Float)
    sodium_mg:      Mapped[float | None] = mapped_column(Float)
    cholesterol_mg: Mapped[float | None] = mapped_column(Float)
    potassium_mg:   Mapped[float | None] = mapped_column(Float)

    # ── Vitamins ─────────────────────────────────────────────────────────────
    vitamin_a_mcg:            Mapped[float | None] = mapped_column(Float)   # RAE
    vitamin_c_mg:             Mapped[float | None] = mapped_column(Float)
    vitamin_d_mcg:            Mapped[float | None] = mapped_column(Float)
    vitamin_e_mg:             Mapped[float | None] = mapped_column(Float)   # alpha-tocopherol
    vitamin_k_mcg:            Mapped[float | None] = mapped_column(Float)
    thiamine_mg:              Mapped[float | None] = mapped_column(Float)   # B1
    riboflavin_mg:            Mapped[float | None] = mapped_column(Float)   # B2
    niacin_mg:                Mapped[float | None] = mapped_column(Float)   # B3
    pantothenic_acid_mg:      Mapped[float | None] = mapped_column(Float)   # B5
    pyridoxine_mg:            Mapped[float | None] = mapped_column(Float)   # B6
    cobalamin_mcg:            Mapped[float | None] = mapped_column(Float)   # B12
    biotin_mcg:               Mapped[float | None] = mapped_column(Float)
    folate_mcg:               Mapped[float | None] = mapped_column(Float)   # DFE
    choline_mg:               Mapped[float | None] = mapped_column(Float)
    retinol_mcg:              Mapped[float | None] = mapped_column(Float)
    alpha_carotene_mcg:       Mapped[float | None] = mapped_column(Float)
    beta_carotene_mcg:        Mapped[float | None] = mapped_column(Float)
    beta_cryptoxanthin_mcg:   Mapped[float | None] = mapped_column(Float)
    lutein_zeaxanthin_mcg:    Mapped[float | None] = mapped_column(Float)
    lycopene_mcg:             Mapped[float | None] = mapped_column(Float)
    beta_tocopherol_mg:       Mapped[float | None] = mapped_column(Float)
    delta_tocopherol_mg:      Mapped[float | None] = mapped_column(Float)
    gamma_tocopherol_mg:      Mapped[float | None] = mapped_column(Float)

    # ── Minerals ─────────────────────────────────────────────────────────────
    calcium_mg:     Mapped[float | None] = mapped_column(Float)
    iron_mg:        Mapped[float | None] = mapped_column(Float)
    magnesium_mg:   Mapped[float | None] = mapped_column(Float)
    phosphorus_mg:  Mapped[float | None] = mapped_column(Float)
    zinc_mg:        Mapped[float | None] = mapped_column(Float)
    copper_mg:      Mapped[float | None] = mapped_column(Float)
    manganese_mg:   Mapped[float | None] = mapped_column(Float)
    selenium_mcg:   Mapped[float | None] = mapped_column(Float)
    chromium_mcg:   Mapped[float | None] = mapped_column(Float)
    iodine_mcg:     Mapped[float | None] = mapped_column(Float)
    molybdenum_mcg: Mapped[float | None] = mapped_column(Float)
    fluoride_mg:    Mapped[float | None] = mapped_column(Float)

    # ── Amino acids ──────────────────────────────────────────────────────────
    alanine_g:       Mapped[float | None] = mapped_column(Float)
    arginine_g:      Mapped[float | None] = mapped_column(Float)
    aspartic_acid_g: Mapped[float | None] = mapped_column(Float)
    cystine_g:       Mapped[float | None] = mapped_column(Float)
    glutamic_acid_g: Mapped[float | None] = mapped_column(Float)
    glycine_g:       Mapped[float | None] = mapped_column(Float)
    histidine_g:     Mapped[float | None] = mapped_column(Float)
    hydroxyproline_g:Mapped[float | None] = mapped_column(Float)
    isoleucine_g:    Mapped[float | None] = mapped_column(Float)
    leucine_g:       Mapped[float | None] = mapped_column(Float)
    lysine_g:        Mapped[float | None] = mapped_column(Float)
    methionine_g:    Mapped[float | None] = mapped_column(Float)
    phenylalanine_g: Mapped[float | None] = mapped_column(Float)
    proline_g:       Mapped[float | None] = mapped_column(Float)
    serine_g:        Mapped[float | None] = mapped_column(Float)
    threonine_g:     Mapped[float | None] = mapped_column(Float)
    tryptophan_g:    Mapped[float | None] = mapped_column(Float)
    tyrosine_g:      Mapped[float | None] = mapped_column(Float)
    valine_g:        Mapped[float | None] = mapped_column(Float)

    # ── Fatty acids ──────────────────────────────────────────────────────────
    monounsaturated_fat_g: Mapped[float | None] = mapped_column(Float)
    polyunsaturated_fat_g: Mapped[float | None] = mapped_column(Float)
    omega3_ala_g:          Mapped[float | None] = mapped_column(Float)
    omega3_dha_g:          Mapped[float | None] = mapped_column(Float)
    omega3_epa_g:          Mapped[float | None] = mapped_column(Float)
    omega6_aa_g:           Mapped[float | None] = mapped_column(Float)
    omega6_la_g:           Mapped[float | None] = mapped_column(Float)
    phytosterol_mg:        Mapped[float | None] = mapped_column(Float)

    # ── Carb details & other ─────────────────────────────────────────────────
    soluble_fiber_g:       Mapped[float | None] = mapped_column(Float)
    insoluble_fiber_g:     Mapped[float | None] = mapped_column(Float)
    fructose_g:            Mapped[float | None] = mapped_column(Float)
    galactose_g:           Mapped[float | None] = mapped_column(Float)
    glucose_g:             Mapped[float | None] = mapped_column(Float)
    lactose_g:             Mapped[float | None] = mapped_column(Float)
    maltose_g:             Mapped[float | None] = mapped_column(Float)
    sucrose_g:             Mapped[float | None] = mapped_column(Float)
    oxalate_mg:            Mapped[float | None] = mapped_column(Float)
    phytate_mg:            Mapped[float | None] = mapped_column(Float)
    caffeine_mg:           Mapped[float | None] = mapped_column(Float)
    water_g:               Mapped[float | None] = mapped_column(Float)
    ash_g:                 Mapped[float | None] = mapped_column(Float)
    alcohol_g:             Mapped[float | None] = mapped_column(Float)
    beta_hydroxybutyrate_g:Mapped[float | None] = mapped_column(Float)

    usda_fdc_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    recipe_id:   Mapped[str | None] = mapped_column(ForeignKey("mt_recipes.id", ondelete="SET NULL"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    meal_log_items: Mapped[list["MealLogItem"]]      = relationship("MealLogItem",      back_populates="ingredient")
    recipe_usages:  Mapped[list["RecipeIngredient"]] = relationship("RecipeIngredient", back_populates="ingredient")
    source_recipe:  Mapped["Recipe | None"]          = relationship("Recipe", foreign_keys=[recipe_id])


class Recipe(Base):
    __tablename__ = "mt_recipes"

    id:             Mapped[str]        = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name:           Mapped[str]        = mapped_column(String(500), nullable=False)
    description:    Mapped[str | None] = mapped_column(Text)
    total_weight_g: Mapped[float | None] = mapped_column(Float)
    serving_size_g: Mapped[float | None] = mapped_column(Float)

    calories:       Mapped[float] = mapped_column(Float, default=0.0)
    protein_g:      Mapped[float] = mapped_column(Float, default=0.0)
    fat_g:          Mapped[float] = mapped_column(Float, default=0.0)
    carbs_g:        Mapped[float] = mapped_column(Float, default=0.0)
    sodium_mg:      Mapped[float] = mapped_column(Float, default=0.0)
    cholesterol_mg: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    ingredients:    Mapped[list["RecipeIngredient"]] = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    meal_log_items: Mapped[list["MealLogItem"]]      = relationship("MealLogItem",      back_populates="recipe")


class RecipeIngredient(Base):
    __tablename__ = "mt_recipe_ingredients"

    id:            Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    recipe_id:     Mapped[str]   = mapped_column(ForeignKey("mt_recipes.id",     ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[str]   = mapped_column(ForeignKey("mt_ingredients.id", ondelete="CASCADE"), nullable=False)
    quantity_g:    Mapped[float] = mapped_column(Float, nullable=False)

    recipe:     Mapped["Recipe"]     = relationship("Recipe",     back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship("Ingredient", back_populates="recipe_usages")


class MealLog(Base):
    __tablename__ = "mt_meal_logs"
    __table_args__ = (UniqueConstraint("user_id", "log_date", "meal_number", name="uq_mt_user_date_meal"),)

    id:          Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:     Mapped[str]   = mapped_column(ForeignKey("mt_users.id", ondelete="CASCADE"), nullable=False)
    log_date:    Mapped[date]  = mapped_column(Date, nullable=False)
    meal_number: Mapped[int]   = mapped_column(Integer, nullable=False)

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    total_calories:       Mapped[float] = mapped_column(Float, default=0.0)
    total_protein_g:      Mapped[float] = mapped_column(Float, default=0.0)
    total_fat_g:          Mapped[float] = mapped_column(Float, default=0.0)
    total_carbs_g:        Mapped[float] = mapped_column(Float, default=0.0)
    total_sodium_mg:      Mapped[float] = mapped_column(Float, default=0.0)
    total_cholesterol_mg: Mapped[float] = mapped_column(Float, default=0.0)

    user:  Mapped["User"]              = relationship("User",        back_populates="meal_logs")
    items: Mapped[list["MealLogItem"]] = relationship("MealLogItem", back_populates="meal_log",
                                                      cascade="all, delete-orphan",
                                                      order_by="MealLogItem.logged_at")


class MealLogItem(Base):
    __tablename__ = "mt_meal_log_items"

    id:            Mapped[str]        = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    meal_log_id:   Mapped[str]        = mapped_column(ForeignKey("mt_meal_logs.id",   ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[str | None] = mapped_column(ForeignKey("mt_ingredients.id", ondelete="SET NULL"))
    recipe_id:     Mapped[str | None] = mapped_column(ForeignKey("mt_recipes.id",     ondelete="SET NULL"))

    quantity_g:   Mapped[float] = mapped_column(Float, nullable=False)
    display_name: Mapped[str]   = mapped_column(String(500), nullable=False)

    calories:       Mapped[float] = mapped_column(Float, default=0.0)
    protein_g:      Mapped[float] = mapped_column(Float, default=0.0)
    fat_g:          Mapped[float] = mapped_column(Float, default=0.0)
    carbs_g:        Mapped[float] = mapped_column(Float, default=0.0)
    sodium_mg:      Mapped[float] = mapped_column(Float, default=0.0)
    cholesterol_mg: Mapped[float] = mapped_column(Float, default=0.0)

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meal_log:   Mapped["MealLog"]           = relationship("MealLog",     back_populates="items")
    ingredient: Mapped["Ingredient | None"] = relationship("Ingredient", back_populates="meal_log_items")
    recipe:     Mapped["Recipe | None"]     = relationship("Recipe",     back_populates="meal_log_items")
    components: Mapped[list["MealLogItemComponent"]] = relationship(
        "MealLogItemComponent", back_populates="meal_log_item", cascade="all, delete-orphan"
    )


class MealLogItemComponent(Base):
    """
    Snapshot of a recipe's sub-ingredients at the time a recipe was logged.

    When a recipe is logged to a meal, each ingredient in the recipe is
    recorded here (scaled to the quantity_g of the log item). This lets
    you later analyse which specific foods contributed to a logged meal
    even when the original recipe may change.

    quantity_g here is already scaled — e.g. if you log 150g of a 300g
    recipe that contains 200g chicken + 100g rice, we store 100g chicken
    and 50g rice.
    """
    __tablename__ = "mt_meal_log_item_components"

    id:               Mapped[str]        = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    meal_log_item_id: Mapped[str]        = mapped_column(ForeignKey("mt_meal_log_items.id", ondelete="CASCADE"), nullable=False)
    ingredient_id:    Mapped[str | None] = mapped_column(ForeignKey("mt_ingredients.id",    ondelete="SET NULL"))
    ingredient_name:  Mapped[str]        = mapped_column(String(500), nullable=False)   # snapshot
    quantity_g:       Mapped[float]      = mapped_column(Float, nullable=False)         # already scaled

    meal_log_item: Mapped["MealLogItem"]     = relationship("MealLogItem", back_populates="components")
    ingredient:    Mapped["Ingredient | None"] = relationship("Ingredient")


class ApiKey(Base):
    __tablename__ = "mt_api_keys"

    id:           Mapped[str]            = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:      Mapped[str]            = mapped_column(ForeignKey("mt_users.id", ondelete="CASCADE"), nullable=False)
    name:         Mapped[str]            = mapped_column(String(255), nullable=False)
    key_hash:     Mapped[str]            = mapped_column(String(64), nullable=False, unique=True)
    is_active:    Mapped[bool]           = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:   Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="api_keys")
