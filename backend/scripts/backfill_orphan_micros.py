"""
Give Cronometer-imported composite meals their missing micronutrients.

The problem
───────────
`mt_meal_log_items` snapshots only six nutrients (calories, protein, fat, carbs,
sodium, cholesterol). Fibre, vitamins and minerals are recomputed at read time
from the linked ingredient, or by summing `mt_meal_log_item_components`.

Cronometer's import produced composite meals with **neither**: `ingredient_id`
and `recipe_id` both NULL, just a `display_name` and the six macros. Those rows
contribute their calories normally and *zero* micronutrients — which is why
fibre appears to double in June 2026 when the same meals started being logged
as recipes. 32% of pre-June-2026 calories are affected.

What this does
──────────────
For each orphan entry whose name matches a recipe that still exists, it writes
the component rows that were never recorded, scaled so the components' calories
match the calories already on the entry.

  * **Calories come from the entry, not the recipe.** The logged figure is what
    was actually eaten and is authoritative; the recipe only supplies the
    *composition*. Scaling by the calorie ratio means a day you ate half the
    batch gets half the fibre.
  * **Nothing on the entry itself is modified** — no macros, no quantity, and
    `recipe_id` is deliberately left NULL. Aggregation joins components by
    `meal_log_item_id` regardless, and leaving the row alone keeps every
    recipe-specific recalculation path (which would rewrite the macro snapshot)
    out of the picture.
  * Adding components therefore adds micronutrients **only**: `_MICRO_FIELDS`
    and `_SNAPSHOT_FIELDS` share no members, so macros cannot double-count.

Honest limitation: this reconstructs old days from *today's* recipe definition.
Where a recipe has been edited since, the backfill applies the current version.
It is an estimate of what was eaten, far closer than the zero that is there now,
but it is not a record.

    python3.13 scripts/backfill_orphan_micros.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (Ingredient, MealLog, MealLogItem,
                               MealLogItemComponent, Recipe, RecipeIngredient)

# A scale factor outside this range means the entry and the recipe are not the
# same dish (or the recipe was redefined beyond recognition). Skip and report
# rather than invent a portion.
#
# The floor has to be very low because batch recipes are legitimately eaten a
# fraction at a time: "Lean granola" is a 5,943 kcal batch served ~150 kcal at
# a time, a factor of 0.025. An earlier 0.10 floor rejected all 123 of those as
# implausible when they are the most ordinary case there is.
MIN_FACTOR, MAX_FACTOR = 0.004, 4.0


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    engine = create_async_engine(os.environ["DBURL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        # Recipe composition, and what that composition comes to in calories.
        rows = (await db.execute(
            select(Recipe.name, RecipeIngredient.ingredient_id,
                   RecipeIngredient.quantity_g, Ingredient)
            .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
            .join(Ingredient, RecipeIngredient.ingredient_id == Ingredient.id)
        )).all()

        recipes: dict[str, list] = defaultdict(list)
        for name, ing_id, qty, ing in rows:
            recipes[norm(name)].append((ing_id, ing.name, qty or 0.0, ing))

        totals: dict[str, float] = {}
        for key, parts in recipes.items():
            kcal = 0.0
            for _, _, qty, ing in parts:
                base = ing.serving_size_g or 100.0
                kcal += (ing.calories or 0.0) * (qty / base if base else 0.0)
            totals[key] = kcal

        # Orphans: no ingredient, no recipe, and no components already.
        has_comp = select(MealLogItemComponent.meal_log_item_id).distinct().subquery()
        orphans = (await db.execute(
            select(MealLogItem, MealLog.log_date)
            .join(MealLog, MealLog.id == MealLogItem.meal_log_id)
            .outerjoin(has_comp, has_comp.c.meal_log_item_id == MealLogItem.id)
            .where(MealLogItem.ingredient_id.is_(None),
                   MealLogItem.recipe_id.is_(None),
                   has_comp.c.meal_log_item_id.is_(None))
            .order_by(MealLog.log_date)
        )).all()

        print(f"orphan entries with no components: {len(orphans)}")

        matched = skipped_nomatch = skipped_factor = 0
        added_components = 0
        unmatched: dict[str, int] = defaultdict(int)
        per_recipe: dict[str, int] = defaultdict(int)
        first_date = last_date = None

        for item, log_date in orphans:
            key = norm(item.display_name)
            parts = recipes.get(key)
            if not parts or not totals.get(key):
                skipped_nomatch += 1
                unmatched[item.display_name or "(no name)"] += 1
                continue

            factor = (item.calories or 0.0) / totals[key]
            if not (MIN_FACTOR <= factor <= MAX_FACTOR):
                skipped_factor += 1
                continue

            if args.limit and matched >= args.limit:
                break
            matched += 1
            per_recipe[item.display_name] += 1
            first_date = first_date or log_date
            last_date = log_date

            for ing_id, ing_name, qty, _ing in parts:
                if not qty:
                    continue
                db.add(MealLogItemComponent(
                    meal_log_item_id=item.id,
                    ingredient_id=ing_id,
                    ingredient_name=ing_name,
                    quantity_g=round(qty * factor, 3),
                ))
                added_components += 1

        print(f"  matched a current recipe : {matched}")
        print(f"  no matching recipe       : {skipped_nomatch}")
        print(f"  implausible portion      : {skipped_factor}")
        print(f"  component rows to write  : {added_components}")
        if first_date:
            print(f"  dates covered            : {first_date} .. {last_date}")

        print("\n  entries per meal:")
        for name, n in sorted(per_recipe.items(), key=lambda kv: -kv[1])[:12]:
            print(f"     {name[:44]:<46} {n}")
        if unmatched:
            print("\n  most common unmatched names (left untouched):")
            for name, n in sorted(unmatched.items(), key=lambda kv: -kv[1])[:10]:
                print(f"     {name[:44]:<46} {n}")

        if args.dry_run:
            await db.rollback()
            print("\n(dry run — nothing written)")
        else:
            await db.commit()
            print(f"\nDONE  wrote {added_components} component rows for {matched} entries")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
