"""
Import a restaurant's published nutrition PDF from a link.

Two steps, mirroring the recipe importer: `/preview` parses and returns a draft
for review, `/save` writes what the user approved. Nothing is written to the
library until the user has seen the numbers.

The parsing lives in services/restaurant_pdf.py, which recovers the table
layout from the document rather than from a hand-written column map.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Ingredient
from app.services import restaurant_pdf

router = APIRouter(prefix="/foods/restaurant-import", tags=["restaurant-import"])

# Only these ever reach the database. Anything else the client sends back with
# an item is ignored rather than trusted.
NUTRIENT_FIELDS = {
    "calories", "protein_g", "carbs_g", "fat_g", "sat_fat_g", "trans_fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg", "caffeine_mg",
    "serving_size_g",
}


class PreviewRequest(BaseModel):
    url: str
    brand: Optional[str] = None


class ImportItem(BaseModel):
    name: str
    values: dict[str, float] = Field(default_factory=dict)


class SaveRequest(BaseModel):
    brand: str
    items: list[ImportItem]


def _brand_from_url(url: str) -> str:
    """A sensible default the user can correct, taken from the domain."""
    host = (urlparse(url).hostname or "").lower()
    host = re.sub(r"^(www|files|assets|cdn|docs|media)\.", "", host)
    stem = host.split(".")[0] if host else ""
    stem = re.sub(r"[-_]+", " ", stem).strip()
    return stem.title() if stem else ""


@router.post("/preview")
async def preview(body: PreviewRequest) -> dict[str, Any]:
    try:
        pdf = restaurant_pdf.fetch_pdf(body.url)
        guide = restaurant_pdf.parse_guide(pdf)
    except restaurant_pdf.ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:                       # pdfplumber raises freely
        raise HTTPException(
            status_code=422,
            detail=f"That PDF could not be read ({type(exc).__name__}).",
        ) from exc

    def shape(rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            out.append({
                "name": row["name"],
                "reason": row.get("reason"),
                "values": {k: v for k, v in row.items()
                           if k in NUTRIENT_FIELDS and v is not None},
            })
        return out

    return {
        "brand": (body.brand or "").strip() or _brand_from_url(body.url),
        "pages": guide.pages,
        "warnings": guide.warnings,
        "columns": [c for c in guide.columns if c["field"]],
        "items": shape(guide.items),
        "flagged": shape(guide.flagged),
    }


@router.post("/save")
async def save(body: SaveRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    brand = body.brand.strip()
    if not brand:
        raise HTTPException(status_code=400, detail="A restaurant name is required.")
    if not body.items:
        raise HTTPException(status_code=400, detail="No items were selected.")

    # One query rather than one per item: these guides run to 500+ rows.
    existing = {
        row.name: row
        for row in (await db.execute(
            select(Ingredient).where(func.lower(Ingredient.brand) == brand.lower())
        )).scalars()
    }

    created = updated = 0
    for item in body.items:
        name = re.sub(r"\s+", " ", item.name).strip()
        if not name:
            continue
        values = {k: v for k, v in item.values.items() if k in NUTRIENT_FIELDS}
        if not values.get("calories"):
            continue

        row = existing.get(name)
        if row is None:
            row = Ingredient(source="restaurant", brand=brand, name=name)
            db.add(row)
            existing[name] = row
            created += 1
        else:
            updated += 1

        for column, value in values.items():
            setattr(row, column, value)
        # A guide with no published gram weights leaves serving_size_g unset,
        # which the app reads as "per 100 g" and would scale wrongly. Naming the
        # serving puts it on the serving-only path instead. See the serving-size
        # invariant in CLAUDE.md.
        if values.get("serving_size_g"):
            row.serving_size_desc = "1 serving"
        else:
            row.serving_size_g = None
            row.serving_size_desc = "1 serving"

    await db.commit()
    return {"brand": brand, "created": created, "updated": updated}
