"""Food-form compatibility for recipe ingredient matching.

Ingredient search is intentionally broad: a query for ``milk`` can retrieve
whole milk, dry milk, evaporated milk, sheep milk, and milk substitutes. Word
matching alone cannot tell which of those is appropriate. This module applies
small, inspectable semantic penalties before source popularity or name length
decide the winner.

It is deliberately a guardrail, not a nutrition model. If the recipe explicitly
asks for a form (``powdered milk``, ``goat milk``), that form is preferred. If
it does not, a materially different form is demoted or surfaced for review.
"""
from __future__ import annotations

import re
from typing import Iterable


def tokens(text: str) -> set[str]:
    return {word for word in re.split(r"[^a-z0-9]+", (text or "").lower()) if word}


# These are forms of a food, not harmless descriptive words. A generic recipe
# line should never silently land on one of them when an ordinary equivalent is
# available. Terms are grouped so an explicit request for any term in the group
# permits that form.
_FORM_GROUPS = {
    "dry": {"dry", "dried", "powder", "powdered", "dehydrated", "instant"},
    "concentrated": {"condensed", "evaporated", "concentrate", "paste"},
    "preserved": {"canned", "tinned", "jarred", "frozen"},
    "liquid_product": {"juice", "broth", "stock", "soup", "drink"},
    "prepared": {"fried", "breaded", "battered", "cooked", "smoked", "pickled"},
    "substitute": {"substitute", "imitation", "nondairy", "non", "dairy", "plant"},
    "flavoured": {
        "flavoured", "flavored", "fruit", "vanilla", "chocolate",
        "strawberry", "toffee", "hazelnut",
    },
    # Finished foods that merely contain the requested ingredient. A plain
    # recipe line such as "cinnamon" must resolve to the spice, not a cinnamon
    # bun or cereal. Explicit queries ("cinnamon bun") still permit the form.
    "composite": {
        "bar", "biscuit", "bread", "bun", "cake", "candy", "cereal",
        "cookie", "cracker", "dessert", "muffin", "oatmeal", "pastry",
        "porridge", "pudding", "roll", "toast",
    },
}

_MILK_SPECIES = {"human", "sheep", "goat", "buffalo", "camel", "mare"}
_MILK_LOW_FAT = {"skim", "skimmed", "nonfat", "fatfree", "low", "reduced", "zero"}

# Verified nutrient databases often prefix a generic ingredient with its food
# class ("Spices, cinnamon, ground"). That is still a direct identity match,
# unlike a finished food whose first word happens to be cinnamon.
_GENERIC_NAME_PREFIXES = {"spice", "spices", "herb", "herbs"}


def has_identity_head(query_words: Iterable[str], candidate_name: str) -> bool:
    """Whether the candidate begins with the requested food identity."""
    wanted = {word.rstrip("s") for word in query_words}
    candidate = [word.rstrip("s") for word in re.split(
        r"[^a-z0-9]+", (candidate_name or "").lower()
    ) if word]
    if not candidate:
        return False
    if candidate[0] in wanted:
        return True
    return (
        candidate[0] in _GENERIC_NAME_PREFIXES
        and len(candidate) > 1
        and candidate[1] in wanted
    )


def form_penalty(query_words: Iterable[str], candidate_name: str) -> int:
    """How incompatible a candidate form is with the requested ingredient.

    ``0`` means compatible. Values of 8+ are substantial enough that callers
    should not auto-select the candidate when a better option exists.
    """
    wanted = {word.rstrip("s") for word in query_words}
    candidate = {word.rstrip("s") for word in tokens(candidate_name)}
    penalty = 0

    for group_words in _FORM_GROUPS.values():
        group = {word.rstrip("s") for word in group_words}
        if candidate & group and not wanted & group:
            penalty += 8

    # Plain milk is conventionally liquid whole cow's milk in recipes. These
    # are preferences, not prohibitions: explicit qualifiers always win.
    if "milk" in wanted:
        if candidate & _MILK_SPECIES and not wanted & _MILK_SPECIES:
            penalty += 7
        if candidate & _MILK_LOW_FAT and not wanted & _MILK_LOW_FAT:
            penalty += 4
        if "whole" in wanted and "whole" not in candidate:
            penalty += 5

    return penalty


def is_unsafe_automatic_match(query_words: Iterable[str], candidate_name: str) -> bool:
    """Whether an automatic match would be a materially different food form."""
    return form_penalty(query_words, candidate_name) >= 8
