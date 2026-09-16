"""
Parse any restaurant's published nutrition-guide PDF without a hand-written
column map.

The chain-specific importer this replaces needed a human to read each guide and
record the x-position of every column. That does not scale to "paste a link",
so the layout is recovered from the document itself:

  1. **Find the columns.** Cluster the x-positions of every numeric word in the
     document. Real nutrient columns appear on nearly every row, so clusters
     holding at least 60% of the busiest cluster's members are the table; stray
     numbers inside item names ("2 oz") fall far below that line.

  2. **Identify the columns by what the numbers *mean*.** Header text is not
     dependable — Panera stores its headers reversed ("eziS gnivreS"), TGI
     splits them across lines, and body text sitting near a column poisons any
     keyword match. But `4·protein + 4·carbs + 9·fat ≈ calories` holds for real
     food, so the calories/fat/carbs/protein columns are found by searching for
     the combination that satisfies it across the whole document. The equation
     that validates the import also discovers it.

     Two constraints keep the search honest. Calories must dominate the macros
     it is compared against, otherwise a guide full of zero-calorie drinks
     (TGI's bar menu) lets an all-zero combination fit perfectly. And carbs sit
     left of protein, because every nutrition label follows FDA order.

  3. **Fill in the rest by label order.** Between fat and carbs a label always
     reads saturated, trans, cholesterol, sodium; between carbs and protein,
     fibre then sugar. Header keywords are used to confirm these, never to
     decide them alone.

Rows whose macros do not reconcile with their calories are returned as
`flagged` rather than dropped: the cause is usually the publisher's own typo
(TGI lists boneless wings at 310 kcal with 33g of fat, which is 297 kcal by
itself) or alcohol, which carries 7 kcal/g and is not a printed macro. The
caller decides what to do with them.
"""
from __future__ import annotations

import collections
import io
import itertools
import re
import statistics
from dataclasses import dataclass, field as dc_field

import httpx
import pdfplumber

# Identify ourselves honestly. Note that a spoofed browser User-Agent is
# actively worse: panerabread.com returns 403 to a fake Chrome string and 200
# to this one.
UA = "MacroTrackerPersonal/1.0 (personal nutrition tracker)"

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PAGES = 60

COL_GAP = 8.0           # x-distance that still counts as the same column
COL_TOLERANCE = 14.0    # how far a value may sit from its column centre
LINE_TOLERANCE = 4.0    # vertical gap that still counts as the same row
WRAP_MAX_GAP = 14.0     # a wrapped name is never further than one row away
COLUMN_MIN_SHARE = 0.60 # of the busiest cluster, to count as a real column
NAME_MARGIN = 8.0

ENERGY_TOLERANCE = 0.15
ENERGY_FLOOR_KCAL = 35  # small items round hard; a flat % is unfair to them
MIN_ANCHOR_ROWS = 10
MAX_ANCHOR_ERROR = 0.20

NUMERIC = re.compile(r"^(?:[\d,]+(?:\.\d+)?|N/A|--|<\d+)$")

# Canonical FDA label order, used to fill the gaps between the anchors.
BETWEEN_FAT_AND_CARBS = ["sat_fat_g", "trans_fat_g", "cholesterol_mg", "sodium_mg"]
BETWEEN_CARBS_AND_PROTEIN = ["fiber_g", "sugar_g"]

# Header keywords, used only to confirm a positional guess or to name a column
# outside the anchored range (caffeine, serving size).
HINTS = [
    ("trans", "trans_fat_g"), ("sat", "sat_fat_g"), ("chol", "cholesterol_mg"),
    ("sod", "sodium_mg"), ("fib", "fiber_g"), ("sug", "sugar_g"),
    ("prot", "protein_g"), ("caffein", "caffeine_mg"), ("carb", "carbs_g"),
    ("fat", "fat_g"), ("cal", "calories"), ("serv", "serving"), ("size", "serving"),
]
IGNORE_HINT = re.compile(r"\b(vit|calcium|iron)|%")

SKIP_NAME = re.compile(
    r"^(serving|nutrition|nutritional|some |only standard|daily|calories|"
    r"milligrams|preparation|laboratory|the actual|effective|revised|"
    r"before placing|to our guests|regular kitchen|\d{1,2}/\d{1,2}/\d{4}|"
    # "less than 1 g" is a value Olive Garden prints as words; it lands on a
    # line of its own and would otherwise be read as an item name.
    r"less\b|\W*$)",
    re.I,
)


@dataclass
class ParsedGuide:
    items: list[dict] = dc_field(default_factory=list)
    flagged: list[dict] = dc_field(default_factory=list)
    columns: list[dict] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    pages: int = 0


class ParseError(RuntimeError):
    """The PDF could not be read as a nutrition table."""


def fetch_pdf(url: str) -> bytes:
    if not re.match(r"^https?://", url.strip(), re.I):
        raise ParseError("That does not look like a web address.")
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.get(url.strip(), headers={"User-Agent": UA,
                                                 "Accept": "application/pdf,*/*"})
            r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ParseError(
            f"The site returned {exc.response.status_code} for that link. "
            "Some chains block automated downloads; try the direct PDF address."
        ) from exc
    except httpx.HTTPError as exc:
        raise ParseError(f"Could not download that link ({type(exc).__name__}).") from exc

    body = r.content
    if len(body) > MAX_PDF_BYTES:
        raise ParseError("That PDF is larger than 25 MB.")
    if not body.startswith(b"%PDF"):
        raise ParseError("That link is not a PDF file.")
    return body


# A menu section whose heading carries a lowercase explanation, so the
# "headings are all-caps" test does not catch it — Earls prints
# "MAINS (includes sides unless otherwise noted...)" on its own line, which
# would otherwise be glued onto the first dish under it.
SECTION_HEADING = re.compile(r"^[A-Z][A-Z0-9 &'/+-]{2,}\s*\(")

_HEADER_WORD = re.compile(
    r"^(cals?|calories|fat|sat|saturated|trans|chol|cholesterol|sodium|sod|"
    r"carb|carbs|carbohydrates?|fib|fibre|fiber|sug|sugars?|prot|protein|"
    r"serving|servings|size|caffeine|vit|vitamin|calcium|iron|dv)$"
)
_UNIT_WORD = re.compile(r"^(g|mg|mcg|kcal)$")


def _looks_like_header(text: str) -> bool:
    """
    True for a line that names columns rather than an item.

    Needed because a line with no figures is otherwise taken as an item name,
    and header rows have no figures either. Panera's headers are stored
    right-to-left, so they arrive as "taF taF )g( )g(" and would be prefixed
    onto the first real item on every page; Olive Garden's "less than 1 g"
    cells would become names of their own.

    Two hits are required so an ordinary item keeps its name — "Low Fat Milk"
    scores one and survives.
    """
    hits = 0
    for token in text.split():
        stripped = re.sub(r"[^a-z]", "", token.lower())
        reversed_ = re.sub(r"[^a-z]", "", token[::-1].lower())
        if _UNIT_WORD.match(stripped):
            hits += 1
        elif _HEADER_WORD.match(stripped) or _HEADER_WORD.match(reversed_):
            hits += 1
    return hits >= 2


def _to_float(text: str | None) -> float | None:
    if text in (None, "", "N/A", "--"):
        return None
    try:
        return float(str(text).replace(",", "").lstrip("<"))
    except ValueError:
        return None


def _read_pages(body: bytes) -> list[list[dict]]:
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        if not pdf.pages:
            raise ParseError("That PDF has no pages.")
        return [p.extract_words() for p in pdf.pages[:MAX_PAGES]]


def _find_columns(pages: list[list[dict]]) -> list[float]:
    xs = sorted(w["x0"] for ws in pages for w in ws if NUMERIC.match(w["text"]))
    if not xs:
        raise ParseError(
            "No numbers found in that PDF. If it is a scanned image rather than "
            "a text document, the figures cannot be read."
        )
    groups: list[list[float]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= COL_GAP:
            groups[-1].append(x)
        else:
            groups.append([x])
    busiest = max(len(g) for g in groups)
    return [round(statistics.median(g), 1) for g in groups
            if len(g) / busiest >= COLUMN_MIN_SHARE]


def _drop_repeated_half(page_rows: list[list[dict]]) -> tuple[list[list[dict]], bool]:
    """
    Bilingual guides print the whole table twice — The Keg's pages 10-18 repeat
    pages 1-9 in French. The names differ, so name-matching cannot catch it,
    but the figures are identical. Comparing the numbers in each half is
    decisive: the overlap is 95%+ on a repeated guide and under 5% otherwise.

    Deduplicating on figures alone would be wrong — P.F. Chang's GF White Rice
    legitimately matches its White Rice, and two Panera syrups share a row — so
    this only ever drops a whole trailing half.
    """
    if len(page_rows) < 4:
        return page_rows, False
    half = len(page_rows) // 2

    def sigs(pages):
        return collections.Counter(
            tuple(sorted(r["cells"].items()))
            for p in pages for r in p if len(r["cells"]) >= 4
        )

    first, second = sigs(page_rows[:half]), sigs(page_rows[half:])
    if not first or not second:
        return page_rows, False
    shared = sum((first & second).values())
    if shared / sum(second.values()) >= 0.70:
        return page_rows[:half], True
    return page_rows, False


def _read_rows(pages: list[list[dict]], colxs: list[float]) -> list[dict]:
    """Every line of the document, as a name plus whatever landed in columns."""
    name_max_x = min(colxs) - NAME_MARGIN
    out: list[dict] = []
    for ws in pages:
        lines: list[list[dict]] = []
        for w in sorted(ws, key=lambda w: w["top"]):
            if lines and w["top"] - lines[-1][0]["top"] <= LINE_TOLERANCE:
                lines[-1].append(w)
            else:
                lines.append([w])
        page_rows = []
        for lw in lines:
            lw = sorted(lw, key=lambda w: w["x0"])
            cells: dict[float, float | None] = {}
            for w in lw:
                if w["x0"] < name_max_x or not NUMERIC.match(w["text"]):
                    continue
                near = min(colxs, key=lambda c: abs(c - w["x0"]))
                if abs(near - w["x0"]) <= COL_TOLERANCE and near not in cells:
                    cells[near] = _to_float(w["text"])

            # On a row carrying figures, the name is whatever sits left of the
            # table. On a row carrying none, the whole line is the name wherever
            # it sits: Olive Garden centres each item's name on its own line,
            # directly above the number columns, so keying off x alone reads
            # every one of its items as nameless.
            if len(cells) >= 4:
                name = " ".join(w["text"] for w in lw if w["x0"] < name_max_x)
            else:
                name = " ".join(w["text"] for w in lw)
            page_rows.append({
                "name": re.sub(r"\s+", " ", name).strip(" .*†‡"),
                "cells": cells,
                "top": lw[0]["top"],
                "bottom": max(w["bottom"] for w in lw),
            })
        out.append(page_rows)
    return out


def _header_hints(pages: list[list[dict]], colxs: list[float]) -> dict[float, str]:
    """Words from header-looking lines, gathered per column. Advisory only."""
    key = re.compile(r"\b(cal|fat|sat|trans|chol|sod|carb|fib|sug|prot|serv|size|"
                     r"caffein|vit|calcium|iron|dv)")
    bag: dict[float, set[str]] = {c: set() for c in colxs}
    for ws in pages:
        lines: dict[int, list[dict]] = {}
        for w in ws:
            lines.setdefault(round(w["top"] / 4) * 4, []).append(w)
        for lw in lines.values():
            toks = []
            for w in lw:
                if NUMERIC.match(w["text"]):
                    continue
                text = re.sub(r"[^a-z% ]", " ", w["text"].lower()).strip()
                if not key.search(text):
                    # Panera's header row is stored right-to-left.
                    reversed_text = re.sub(r"[^a-z% ]", " ", w["text"][::-1].lower()).strip()
                    if not key.search(reversed_text):
                        continue
                    text = reversed_text
                toks.append((w["x0"], text))
            if len(toks) < 3:        # a real header row names several columns
                continue
            for x, text in toks:
                near = min(colxs, key=lambda c: abs(c - x))
                if abs(near - x) <= 22:
                    bag[near].add(text)
    return {c: " ".join(sorted(v)) for c, v in bag.items()}


def _hint_field(text: str) -> str | None:
    if not text or IGNORE_HINT.search(text):
        return None
    if re.search(r"\bcal", text) and re.search(r"\bfat", text):
        return None                      # "Cals From Fat"
    for keyword, field in HINTS:
        if re.search(rf"\b{keyword}", text):
            return field
    return None


def _find_anchors(rows: list[dict], colxs: list[float]) -> tuple[float, float, float, float]:
    """calories / fat / carbs / protein, found via the energy equation."""
    sample = [r["cells"] for r in rows if len(r["cells"]) >= len(colxs) - 1][:200]
    if len(sample) < MIN_ANCHOR_ROWS:
        raise ParseError("That PDF does not contain a readable nutrition table.")

    medians = {}
    for c in colxs:
        vals = [s[c] for s in sample if s.get(c) is not None]
        medians[c] = statistics.median(vals) if vals else 0.0

    best: tuple[float, tuple] | None = None
    for kc, pc, cc, fc in itertools.permutations(colxs, 4):
        # Calories must dominate, or a guide full of zero-calorie drinks lets an
        # all-zero combination fit the equation perfectly.
        if medians[kc] < 50 or medians[kc] <= max(medians[pc], medians[cc], medians[fc]):
            continue
        errs = []
        for s in sample:
            k, p, c, f = s.get(kc), s.get(pc), s.get(cc), s.get(fc)
            if None in (k, p, c, f) or k < 50:
                continue
            errs.append(abs(4 * p + 4 * c + 9 * f - k) / k)
        if len(errs) >= MIN_ANCHOR_ROWS:
            score = statistics.median(errs)
            if best is None or score < best[0]:
                best = (score, (kc, pc, cc, fc))

    if best is None or best[0] > MAX_ANCHOR_ERROR:
        raise ParseError(
            "Could not work out which columns hold calories, fat, carbs and "
            "protein. This guide's layout is not one this importer can read."
        )
    _, (kc, pc, cc, fc) = best
    # 4·protein and 4·carbs are interchangeable in the equation, so the fit
    # cannot tell them apart. Every nutrition label prints carbs before protein.
    carbs, protein = (pc, cc) if pc < cc else (cc, pc)
    return kc, fc, carbs, protein


def _assign_columns(colxs: list[float], anchors, hints: dict[float, str]) -> dict[float, str | None]:
    kcal_x, fat_x, carbs_x, protein_x = anchors
    fields: dict[float, str | None] = {c: None for c in colxs}
    fields[kcal_x], fields[fat_x] = "calories", "fat_g"
    fields[carbs_x], fields[protein_x] = "carbs_g", "protein_g"

    def fill(gap: list[float], canonical: list[str]) -> None:
        # Prefer a header that names the column; otherwise fall back on label
        # order, anchoring to the right so a missing leading column (a guide
        # with no trans-fat column) does not shift everything.
        for i, x in enumerate(gap):
            hinted = _hint_field(hints.get(x, ""))
            if hinted in canonical:
                fields[x] = hinted
            elif len(gap) <= len(canonical):
                fields[x] = canonical[len(canonical) - len(gap) + i]

    fill([c for c in colxs if fat_x < c < carbs_x], BETWEEN_FAT_AND_CARBS)
    fill([c for c in colxs if carbs_x < c < protein_x], BETWEEN_CARBS_AND_PROTEIN)

    # Outside the anchored range only a header can name a column, and only
    # caffeine and serving size are worth taking. Everything else (calories
    # from fat, %DV vitamins) stays unimported.
    for x in colxs:
        if fields[x] is None and (x < kcal_x or x > protein_x):
            hinted = _hint_field(hints.get(x, ""))
            if hinted in ("caffeine_mg", "serving"):
                fields[x] = hinted

    # A duplicate would silently overwrite; keep the one the anchors chose.
    seen: set[str] = set()
    for x in colxs:
        f = fields[x]
        if f and f in seen:
            fields[x] = None
        elif f:
            seen.add(f)
    return fields


def _energy_check(data: dict) -> tuple[bool, float, float]:
    p, c, f = data.get("protein_g"), data.get("carbs_g"), data.get("fat_g")
    kcal = data.get("calories") or 0.0
    if None in (p, c, f):
        return True, 0.0, 0.0
    implied = 4 * p + 4 * c + 9 * f
    # Some chains cost calories on net carbs (Panera's black bean soup is 41g
    # carbs of which 18g is fibre), so accept either basis.
    implied_net = implied - 4 * min(data.get("fiber_g") or 0.0, c)
    allowed = max(kcal * ENERGY_TOLERANCE, ENERGY_FLOOR_KCAL)
    ok = min(abs(implied - kcal), abs(implied_net - kcal)) <= allowed
    return ok, implied, kcal


def parse_guide(body: bytes) -> ParsedGuide:
    pages = _read_pages(body)
    colxs = _find_columns(pages)
    if len(colxs) < 4:
        raise ParseError("That PDF does not have enough numeric columns to be a "
                         "nutrition table.")

    page_rows = _read_rows(pages, colxs)
    page_rows, repeated = _drop_repeated_half(page_rows)
    flat = [r for pr in page_rows for r in pr]
    anchors = _find_anchors(flat, colxs)
    hints = _header_hints(pages, colxs)
    fields = _assign_columns(colxs, anchors, hints)

    serving_x = next((x for x, f in fields.items() if f == "serving"), None)
    serving_vals = [r["cells"].get(serving_x) for r in flat
                    if serving_x is not None and r["cells"].get(serving_x)]
    # A serving column is only a weight if it is headed "size" and the numbers
    # are big enough to be grams. P.F. Chang's column reads 1 on every row (a
    # count) and Panera's is text ("1 Bagel"), of which only the 1 survives.
    serving_is_grams = bool(
        serving_x is not None and serving_vals
        and re.search(r"\bsize", hints.get(serving_x, ""))
        and statistics.median(serving_vals) >= 20
    )

    guide = ParsedGuide(pages=len(page_rows))
    if repeated:
        guide.warnings.append(
            "The second half of this guide repeats the first with the same "
            "figures (usually a second language), so it was skipped."
        )
    guide.columns = [
        {"x": x,
         "field": ("serving_size_g" if fields[x] == "serving" and serving_is_grams
                   else None if fields[x] == "serving" else fields[x]),
         "header": hints.get(x, "")[:40]}
        for x in colxs
    ]
    if not serving_is_grams:
        guide.warnings.append(
            "This guide publishes no gram weights, so each item is stored as "
            "one serving and cannot be logged by weight."
        )

    required = {"calories", "fat_g", "carbs_g", "protein_g"}
    value_fields = {x: f for x, f in fields.items() if f and f != "serving"}
    if serving_is_grams:
        value_fields[serving_x] = "serving_size_g"

    seen: set[str] = set()
    for rows in page_rows:
        consumed: set[int] = set()

        def is_wrap(i: int) -> bool:
            return (0 <= i < len(rows) and bool(rows[i]["name"])
                    and len(rows[i]["cells"]) < 4
                    and not SKIP_NAME.match(rows[i]["name"])
                    and not _looks_like_header(rows[i]["name"])
                    and not SECTION_HEADING.match(rows[i]["name"])
                    and rows[i]["name"] != rows[i]["name"].upper())

        for i, row in enumerate(rows):
            data = {f: row["cells"].get(x) for x, f in value_fields.items()}
            if len([v for v in data.values() if v is not None]) < 4:
                continue
            if not data.get("calories") or data["calories"] <= 0:
                continue

            name = row["name"]
            # Long names wrap around the figures: the head on the line above,
            # the tail on the line below. Only take a tail when a head was
            # found, so a plain item does not swallow its neighbour's line.
            took_prefix = False
            if is_wrap(i - 1) and (i - 1) not in consumed \
                    and row["top"] - rows[i - 1]["bottom"] <= WRAP_MAX_GAP:
                name = f"{rows[i - 1]['name']} {name}".strip()
                consumed.add(i - 1)
                took_prefix = True
            if took_prefix and is_wrap(i + 1) \
                    and rows[i + 1]["top"] - row["bottom"] <= WRAP_MAX_GAP:
                name = f"{name} {rows[i + 1]['name']}".strip()
                consumed.add(i + 1)

            name = re.sub(r"\s+", " ", name).strip(" .*†‡")
            if len(name) < 3 or SKIP_NAME.match(name):
                continue
            key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
            if key in seen:
                continue
            seen.add(key)

            item = {k: v for k, v in data.items() if v is not None}
            item["name"] = name
            ok, implied, kcal = _energy_check(data)
            if ok:
                guide.items.append(item)
            else:
                shortfall = kcal - implied
                item["reason"] = (
                    # Alcohol is the commonest innocent explanation (7 kcal/g,
                    # and never a printed macro), but a publisher typo looks
                    # identical from here, so do not assert which it is.
                    f"{kcal:.0f} kcal printed, {implied:.0f} from its macros"
                    if shortfall > 0 else
                    f"macros come to {implied:.0f} kcal against {kcal:.0f} printed"
                )
                guide.flagged.append(item)

    if not guide.items and not guide.flagged:
        raise ParseError("No menu items could be read from that PDF.")
    if missing := required - {c["field"] for c in guide.columns}:
        guide.warnings.append(f"Columns not found: {', '.join(sorted(missing))}.")
    return guide
