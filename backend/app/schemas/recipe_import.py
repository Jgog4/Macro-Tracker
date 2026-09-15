"""Validated API contracts for URL/pasted-text recipe imports."""
from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"


class PreviewRequest(BaseModel):
    url: Optional[str] = Field(None, max_length=2048)
    text: Optional[str] = Field(None, max_length=100_000)
    locale: Literal["us", "metric", "uk", "au"] = "us"

    @model_validator(mode="after")
    def require_one_source(self):
        has_url = bool(self.url and self.url.strip())
        has_text = bool(self.text and self.text.strip())
        if has_url == has_text:
            raise ValueError("Provide either one recipe URL or pasted ingredients.")
        if has_text and len([line for line in self.text.splitlines() if line.strip()]) > 250:
            raise ValueError("Pasted recipes are limited to 250 ingredient lines.")
        return self


class SaveLine(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    quantity: Optional[float] = Field(None, gt=0, le=1_000_000, allow_inf_nan=False)
    unit: Optional[str] = Field(None, max_length=100)
    unit_is_mass: bool = False
    # An inferred count weight must not become a remembered preference merely
    # because the recipe was saved. The client sets this only after the person
    # changes the gram field themselves.
    weight_was_edited: bool = False
    ingredient_id: Optional[str] = Field(None, pattern=UUID_PATTERN)
    grams: Optional[float] = Field(None, gt=0, le=10_000_000, allow_inf_nan=False)
    include: bool = True
    raw: Optional[str] = Field(None, max_length=2_000)
    alias_learn: bool = False
    fat_retention: float = Field(1.0, ge=0, le=1, allow_inf_nan=False)


class SaveRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    source_url: Optional[str] = Field(None, max_length=2048)
    num_servings: int = Field(1, ge=1, le=1_000)
    cooked_weight_g: Optional[float] = Field(
        None, gt=0, le=10_000_000, allow_inf_nan=False)
    lines: list[SaveLine] = Field(..., min_length=1, max_length=250)
    import_id: Optional[str] = Field(None, pattern=UUID_PATTERN)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Recipe title cannot be blank.")
        return value

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_web_url(cls, value: Optional[str]) -> Optional[str]:
        if value:
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                raise ValueError("Recipe source must be an http:// or https:// URL.")
        return value
