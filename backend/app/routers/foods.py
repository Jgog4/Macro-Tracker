"""
/foods — ingredient CRUD + USDA search + restaurant database lookup.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, select, or_, func, literal_column, text, Numeric
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Ingredient, MealLogItem
from app.schemas.schemas import IngredientCreate, IngredientRead, IngredientUpdate, USDASearchResult
from app.services.usda import search_usda, import_usda_food
from app.services.nutrient_completion import complete_missing_micros

router = APIRouter(prefix="/foods", tags=["Foods"])


def _re_escape(term: str) -> str:
    """Escape a user search term for use inside a POSIX regular expression."""
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", term)


# ── List all ingredients by source ───────────────────────────────────────────

@router.get("/", response_model=list[IngredientRead])
async def list_ingredients(
    source: Optional[str] = Query(None, description="Filter: custom | restaurant | usda"),
    db:     AsyncSession = Depends(get_db),
):
    """
    List all ingredients, optionally filtered by source.
    source=custom returns both 'custom' (photo-scanned) and 'personal' rows.
    """
    stmt = select(Ingredient)
    if source == "custom":
        stmt = stmt.where(or_(Ingredient.source == "custom", Ingredient.source == "personal"))
    elif source:
        stmt = stmt.where(Ingredient.source == source)
    stmt = stmt.order_by(Ingredient.name)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Local database search ─────────────────────────────────────────────────────

@router.get("/search", response_model=list[IngredientRead])
async def search_local_foods(
    q:      str = Query(..., min_length=1, description="Search term"),
    source: Optional[str] = Query(None, description="Filter: usda | restaurant | custom"),
    brand:  Optional[str] = Query(None, description="Filter by brand (e.g. Chipotle)"),
    limit:  int = Query(30, le=100),
    db:     AsyncSession = Depends(get_db),
):
    """
    Search local ingredients by name/brand.
    - Exact substring match first; falls back to trigram fuzzy match for typos.
    - Results sorted by: usage frequency (most logged first), then source rank, then name.
    """
    # Usage frequency subquery — count how many times each ingredient has been logged
    usage_sq = (
        select(MealLogItem.ingredient_id, func.count().label("log_count"))
        .group_by(MealLogItem.ingredient_id)
        .subquery()
    )

    source_rank = case(
        (Ingredient.source == "personal",   0),
        (Ingredient.source == "custom",     1),
        (Ingredient.source == "restaurant", 2),
        (Ingredient.source == "cnf",        3),   # Canadian Nutrient File
        (Ingredient.source == "cofid",      4),   # UK CoFID
        (Ingredient.source == "usda",       5),
        else_=6,
    )
    log_count = func.coalesce(usage_sq.c.log_count, 0)

    # Relevance. Substring matching is kept for *retrieval* so partial typing
    # still works ("ric" → rice), but a bare substring match also drags in
    # nonsense: "rice" matches "Liquorice" and "Licorice" mid-word. So rank by
    # whether the term begins a word (`\m` is a Postgres word-start anchor) —
    # that keeps "White Rice" and prefix-typing, and sinks mid-word accidents.
    q_re = _re_escape(q.lower().strip())
    if q_re:
        relevance = case(
            (func.lower(Ingredient.name).op("~")(r"\m" + q_re), 0),
            (func.lower(func.coalesce(Ingredient.brand, "")).op("~")(r"\m" + q_re), 1),
            else_=2,          # matched only in the middle of a word
        )
    else:
        relevance = literal_column("0")

    # Foods you actually eat come first (that's the point of usage ranking),
    # but cap them so the reference databases always get slots — otherwise a
    # common word like "milk" fills every result with previously-logged foods.
    FAMILIAR_SLOTS = 8

    def _ordered(where, familiar: bool, take: int, first_order=None):
        stmt = (
            select(Ingredient)
            .outerjoin(usage_sq, usage_sq.c.ingredient_id == Ingredient.id)
            .where(where)
            .where(log_count > 0 if familiar else log_count == 0)
            # Recipes carry a proxy row in mt_ingredients (recipe_id set). The
            # recipe itself is returned separately by /recipes/search, so
            # including the proxy here just shows every recipe twice.
            .where(Ingredient.recipe_id.is_(None))
            # Relevance first so mid-word accidents never outrank real matches.
            # Then usage, then source. `length(name)` is a mild tiebreaker that
            # favours the plain staple ("Rice, white, raw") over the elaborate
            # variant when neither has been logged.
            .order_by(*([first_order] if first_order is not None else []),
                      relevance, log_count.desc(), source_rank,
                      func.length(Ingredient.name), Ingredient.name)
            .limit(take)
        )
        if source:
            stmt = stmt.where(Ingredient.source == source)
        if brand:
            stmt = stmt.where(func.lower(Ingredient.brand) == brand.lower())
        return stmt

    async def _mixed(where, first_order=None):
        """Familiar foods first (capped), then fill from everything else."""
        familiar = (await db.execute(_ordered(where, True, min(limit, FAMILIAR_SLOTS), first_order))).scalars().all()
        rest_n = limit - len(familiar)
        rest = (await db.execute(_ordered(where, False, rest_n, first_order))).scalars().all() if rest_n > 0 else []
        combined = familiar + rest
        # If there were few unlogged matches, top back up with more familiar ones.
        if len(combined) < limit:
            extra = (await db.execute(_ordered(where, True, limit, first_order))).scalars().all()
            seen = {i.id for i in combined}
            combined += [i for i in extra if i.id not in seen][: limit - len(combined)]
        return combined

    # ── Try exact substring match (AND across all words) ─────────────────────
    words = [w for w in q.lower().split() if w]
    word_clauses = [
        or_(
            func.lower(Ingredient.name).contains(word),
            func.lower(Ingredient.brand).contains(word),
        )
        for word in words
    ]
    rows = await _mixed(and_(*word_clauses))
    if rows:
        return rows

    # ── Fuzzy fallback: trigram similarity on the full query string ───────────
    q_lower = q.lower().strip()
    # On the typo path, closeness of the match matters more than how often the
    # food is eaten — otherwise "chickn" returns your most-logged foods that
    # happen to be vaguely similar, instead of chicken. Bucket the similarity
    # so near-ties still fall through to the usage ordering below.
    similarity = func.greatest(
        func.word_similarity(q_lower, func.lower(Ingredient.name)),
        func.word_similarity(q_lower, func.lower(func.coalesce(Ingredient.brand, ""))),
    )
    return await _mixed(
        or_(
            func.word_similarity(q_lower, func.lower(Ingredient.name))  > 0.25,
            func.word_similarity(q_lower, func.lower(Ingredient.brand)) > 0.25,
        ),
        first_order=func.round((similarity * 10).cast(Numeric)).desc(),
    )


# ── Restaurant database (your CSV brands) ────────────────────────────────────

@router.get("/restaurant", response_model=list[IngredientRead])
async def list_restaurant_foods(
    brand: Optional[str] = Query(None, description="Chipotle | Cactus Club | Pokerrito"),
    db:    AsyncSession = Depends(get_db),
):
    """Returns all restaurant items, optionally filtered by brand."""
    stmt = select(Ingredient).where(Ingredient.source == "restaurant")
    if brand:
        stmt = stmt.where(func.lower(Ingredient.brand) == brand.lower())
    stmt = stmt.order_by(Ingredient.brand, Ingredient.name)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── USDA FoodData Central ────────────────────────────────────────────────────

@router.get("/usda/search", response_model=list[USDASearchResult])
async def usda_search(
    q:     str = Query(..., min_length=2),
    limit: int = Query(10, le=25),
):
    """
    Proxy the USDA FoodData Central search API.
    Results are NOT automatically saved — use POST /foods/usda/{fdc_id}/import.
    """
    return await search_usda(q, limit)


@router.post("/usda/{fdc_id}/import", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
async def import_usda(
    fdc_id: int,
    db:     AsyncSession = Depends(get_db),
):
    """
    Fetch a USDA food by FDC ID and persist it to the local ingredients table.
    Idempotent — returns existing row if already imported.
    """
    # Check if already imported
    existing = await db.execute(select(Ingredient).where(Ingredient.usda_fdc_id == fdc_id))
    if row := existing.scalar_one_or_none():
        return row

    ingredient = await import_usda_food(fdc_id)
    db.add(ingredient)
    await db.flush()
    return ingredient


# ── Manual CRUD ───────────────────────────────────────────────────────────────

@router.post("/", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    body: IngredientCreate,
    db:   AsyncSession = Depends(get_db),
):
    """Manually create a custom ingredient (e.g. from a nutrition label you read yourself)."""
    ingredient = Ingredient(**body.model_dump())
    db.add(ingredient)
    await db.flush()
    await complete_missing_micros(ingredient)
    await db.flush()
    return ingredient


@router.get("/{ingredient_id}", response_model=IngredientRead)
async def get_ingredient(ingredient_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Ingredient, ingredient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return row


@router.patch("/{ingredient_id}", response_model=IngredientRead)
async def update_ingredient(
    ingredient_id: str,
    body: IngredientUpdate,
    db:   AsyncSession = Depends(get_db),
):
    row = await db.get(Ingredient, ingredient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(row, field, val)
    await db.flush()
    return row


@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingredient(ingredient_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Ingredient, ingredient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    await db.delete(row)
