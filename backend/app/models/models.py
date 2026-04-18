"""
SQLAlchemy ORM models for the Macro Tracker app.

Table overview
──────────────
users              – single-user profile
daily_targets      – per-day macro goals
ingredients        – unified food database (USDA + restaurant + custom)
recipes            – custom multi-ingredient blends (e.g. "Turkey & Rice")
recipe_ingredients – junction: which ingredients in each recipe and at what qty
meal_logs          – one row per meal per day  (Meal 1, Meal 2, …)
meal_log_items     – individual line items inside a meal (ingredient OR recipe)
api_keys           – hashed keys for external tool access (Mac dashboard, etc.)
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


# ── Valid source values (stored as plain strings — avoids PostgreSQL ENUM issues) ──
# "usda" | "restaurant" | "custom" | "recipe"


# ── Helper ────────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    """
    Single-user model. Personal-use app — one row expected.
    """
    __tablename__ = "users"

    id:         Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email:      Mapped[str]      = mapped_column(String(255), unique=True, nullable=False)
    name:       Mapped[str]      = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    targets:   Mapped[list["DailyTarget"]] = relationship("DailyTarget", back_populates="user", cascade="all, delete-orphan")
    meal_logs: Mapped[list["MealLog"]]     = relationship("MealLog",     back_populates="user", cascade="all, delete-orphan")
    api_keys:  Mapped[list["ApiKey"]]      = relationship("ApiKey",      back_populates="user", cascade="all, delete-orphan")


class DailyTarget(Base):
    """
    Macro targets for a given calendar day.
    If no row exists for today, the API falls back to the most recent row.
    """
    __tablename__ = "daily_targets"
    __table_args__ = (UniqueConstraint("user_id", "target_date", name="uq_user_date_target"),)

    id:             Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:        Mapped[str]   = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
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
    """
    Unified nutrition entry — the single source of truth for any food item.

    Covers:
    • USDA items (fetched via API, cached here for offline speed)
    • Restaurant items from your combined_nutrition_database.csv
    • Custom entries created manually or via Vision OCR
    • Macro-expanded recipe summaries (source=RECIPE, recipe_id set)

    All macros are stored **per 100 g** when possible so the recipe engine
    can scale them cleanly.  The serving_size_g field records what "one
    serving" is in grams (e.g. 113 for a Chipotle chicken portion).
    """
    __tablename__ = "ingredients"

    id:             Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source:         Mapped[str]   = mapped_column(String(50), nullable=False, default="custom")

    # Identity
    brand:          Mapped[str | None] = mapped_column(String(255))          # e.g. "Chipotle"
    name:           Mapped[str]        = mapped_column(String(500), nullable=False)
    serving_size_desc: Mapped[str | None] = mapped_column(String(100))       # e.g. "113 g", "1 bowl"
    serving_size_g: Mapped[float | None]  = mapped_column(Float)             # numeric grams per serving

    # Macros — stored as *per serving* values (to match restaurant label reality)
    # Use quantity_g in MealLogItem to scale proportionally.
    calories:        Mapped[float] = mapped_column(Float, default=0.0)
    protein_g:       Mapped[float] = mapped_column(Float, default=0.0)
    fat_g:           Mapped[float] = mapped_column(Float, default=0.0)
    sat_fat_g:       Mapped[float | None] = mapped_column(Float)
    trans_fat_g:     Mapped[float | None] = mapped_column(Float)
    carbs_g:         Mapped[float] = mapped_column(Float, default=0.0)
    fiber_g:         Mapped[float | None] = mapped_column(Float)
    sugar_g:         Mapped[float | None] = mapped_column(Float)
    sodium_mg:       Mapped[float | None] = mapped_column(Float)
    cholesterol_mg:  Mapped[float | None] = mapped_column(Float)

    # External references
    usda_fdc_id:    Mapped[int | None]  = mapped_column(BigInteger, unique=True)
    recipe_id:      Mapped[str | None]  = mapped_column(ForeignKey("recipes.id", ondelete="SET NULL"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    meal_log_items:    Mapped[list["MealLogItem"]]      = relationship("MealLogItem",      back_populates="ingredient")
    recipe_usages:     Mapped[list["RecipeIngredient"]] = relationship("RecipeIngredient", back_populates="ingredient")
    source_recipe:     Mapped["Recipe | None"]          = relationship("Recipe", foreign_keys=[recipe_id])


class Recipe(Base):
    """
    A named blend of ingredients — e.g. "Turkey & Rice", "Cream of Rice".
    The recipe engine computes total macros by summing (ingredient macros × qty_g / serving_g).
    """
    __tablename__ = "recipes"

    id:           Mapped[str]        = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name:         Mapped[str]        = mapped_column(String(500), nullable=False)
    description:  Mapped[str | None] = mapped_column(Text)
    total_weight_g: Mapped[float | None] = mapped_column(Float)   # sum of all ingredient grams
    serving_size_g: Mapped[float | None] = mapped_column(Float)   # one serving in grams

    # Computed totals (refreshed whenever ingredients change)
    calories:       Mapped[float] = mapped_column(Float, default=0.0)
    protein_g:      Mapped[float] = mapped_column(Float, default=0.0)
    fat_g:          Mapped[float] = mapped_column(Float, default=0.0)
    carbs_g:        Mapped[float] = mapped_column(Float, default=0.0)
    sodium_mg:      Mapped[float] = mapped_column(Float, default=0.0)
    cholesterol_mg: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    ingredients:    Mapped[list["RecipeIngredient"]] = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    meal_log_items: Mapped[list["MealLogItem"]]      = relationship("MealLogItem",      back_populates="recipe")


class RecipeIngredient(Base):
    """
    Junction table: maps Ingredient → Recipe with a quantity in grams.
    quantity_g is the weight of *this ingredient* used in one full recipe batch.
    """
    __tablename__ = "recipe_ingredients"

    id:            Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    recipe_id:     Mapped[str]   = mapped_column(ForeignKey("recipes.id",     ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[str]   = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False)
    quantity_g:    Mapped[float] = mapped_column(Float, nullable=False)   # grams of this ingredient in recipe

    recipe:     Mapped["Recipe"]     = relationship("Recipe",     back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship("Ingredient", back_populates="recipe_usages")


class MealLog(Base):
    """
    One row per meal per day.
    meal_number is auto-incremented per user per day by the service layer.
    e.g. Meal 1 at 07:30, Meal 2 at 12:00, Meal 3 at 18:45
    """
    __tablename__ = "meal_logs"
    __table_args__ = (UniqueConstraint("user_id", "log_date", "meal_number", name="uq_user_date_meal"),)

    id:          Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:     Mapped[str]   = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    log_date:    Mapped[date]  = mapped_column(Date, nullable=False)
    meal_number: Mapped[int]   = mapped_column(Integer, nullable=False)  # 1, 2, 3, …

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Denormalised totals (computed and stored for fast dashboard reads)
    total_calories:       Mapped[float] = mapped_column(Float, default=0.0)
    total_protein_g:      Mapped[float] = mapped_column(Float, default=0.0)
    total_fat_g:          Mapped[float] = mapped_column(Float, default=0.0)
    total_carbs_g:        Mapped[float] = mapped_column(Float, default=0.0)
    total_sodium_mg:      Mapped[float] = mapped_column(Float, default=0.0)
    total_cholesterol_mg: Mapped[float] = mapped_column(Float, default=0.0)

    user:  Mapped["User"]             = relationship("User",        back_populates="meal_logs")
    items: Mapped[list["MealLogItem"]] = relationship("MealLogItem", back_populates="meal_log",
                                                      cascade="all, delete-orphan",
                                                      order_by="MealLogItem.logged_at")


class MealLogItem(Base):
    """
    One food entry inside a MealLog.
    Exactly one of (ingredient_id, recipe_id) should be set.

    Macros are snapshotted at log time so historical data is stable
    even if the underlying Ingredient is later edited.
    """
    __tablename__ = "meal_log_items"

    id:            Mapped[str]        = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    meal_log_id:   Mapped[str]        = mapped_column(ForeignKey("meal_logs.id",   ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[str | None] = mapped_column(ForeignKey("ingredients.id", ondelete="SET NULL"))
    recipe_id:     Mapped[str | None] = mapped_column(ForeignKey("recipes.id",     ondelete="SET NULL"))

    # How much was consumed
    quantity_g:    Mapped[float]      = mapped_column(Float, nullable=False)  # grams actually eaten
    display_name:  Mapped[str]        = mapped_column(String(500), nullable=False)  # snapshot of name

    # Snapshotted macros at log time
    calories:       Mapped[float] = mapped_column(Float, default=0.0)
    protein_g:      Mapped[float] = mapped_column(Float, default=0.0)
    fat_g:          Mapped[float] = mapped_column(Float, default=0.0)
    carbs_g:        Mapped[float] = mapped_column(Float, default=0.0)
    sodium_mg:      Mapped[float] = mapped_column(Float, default=0.0)
    cholesterol_mg: Mapped[float] = mapped_column(Float, default=0.0)

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meal_log:   Mapped["MealLog"]         = relationship("MealLog",     back_populates="items")
    ingredient: Mapped["Ingredient | None"] = relationship("Ingredient", back_populates="meal_log_items")
    recipe:     Mapped["Recipe | None"]     = relationship("Recipe",     back_populates="meal_log_items")


class ApiKey(Base):
    """
    Hashed API keys for external tools (Mac dashboard, Google Sheets, etc.).
    The raw key is shown once at creation; only the SHA-256 hash is stored.
    """
    __tablename__ = "api_keys"

    id:           Mapped[str]        = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:      Mapped[str]        = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name:         Mapped[str]        = mapped_column(String(255), nullable=False)      # e.g. "Mac Dashboard"
    key_hash:     Mapped[str]        = mapped_column(String(64),  nullable=False, unique=True)  # SHA-256 hex
    is_active:    Mapped[bool]       = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="api_keys")
