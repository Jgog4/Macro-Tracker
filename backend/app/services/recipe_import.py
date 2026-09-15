"""
Recipe import: fetch a URL (or take pasted text), extract the ingredient list,
and parse each line into structure.

Two disciplines from the spec are load-bearing and deliberately enforced here:

  * Structured data first. schema.org/Recipe JSON-LD gives a clean
    `recipeIngredient` array. Scraping visible text instead is what drags prep
    instructions into MyFitnessPal's ingredient lists.
  * The model parses text; it never produces nutrition. Every number comes from
    the food database downstream. An LLM asked for calories will confidently
    invent them, and they look plausible enough that nobody checks.
"""
from __future__ import annotations

import json
import asyncio
import ipaddress
import re
import socket
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from app.config import get_settings
from app.services.vision_ocr import _TextExtractor, _response_text

settings = get_settings()

FETCH_TIMEOUT = 10.0          # spec: hard timeout, fail into the paste box
MAX_FETCH_BYTES = 2_000_000   # recipe pages should never need an unbounded download
MAX_REDIRECTS = 5
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class ExtractionFailed(Exception):
    """Raised when no recipe could be read — the caller shows the paste box."""


# ── Stage 1: fetch and extract ───────────────────────────────────────────────

def _iter_jsonld(html: str):
    """Yield every JSON object found in ld+json script blocks, flattened."""
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            obj = json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                yield cur
                if "@graph" in cur:
                    stack.append(cur["@graph"])


def _as_text(value: Any) -> str:
    """schema.org fields arrive as strings, dicts, or lists of either."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    if isinstance(value, list):
        return " ".join(filter(None, (_as_text(v) for v in value)))
    return str(value).strip()


def extract_structured(html: str) -> Optional[dict]:
    """Pull a recipe out of schema.org JSON-LD. Returns None if absent."""
    for node in _iter_jsonld(html):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if not any("Recipe" == str(t) for t in types):
            continue
        ingredients = [
            _as_text(i) for i in (node.get("recipeIngredient") or node.get("ingredients") or [])
        ]
        ingredients = [i for i in ingredients if i]
        if len(ingredients) < 2:          # spec: <2 ingredients means failed
            continue
        instructions = node.get("recipeInstructions")
        if isinstance(instructions, list):
            inst = " ".join(_as_text(i) for i in instructions)
        else:
            inst = _as_text(instructions)
        return {
            "title":        _as_text(node.get("name")) or "Imported recipe",
            "yield":        _as_text(node.get("recipeYield")),
            "ingredients":  ingredients,
            "instructions": inst[:4000],
            "method":       "jsonld",
        }
    return None


def _is_public_address(value: str) -> bool:
    """Return True only for globally routable addresses."""
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    # IPv4-mapped IPv6 addresses inherit the IPv4 address's classification.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global


async def _validate_public_url(url: str) -> str:
    """Reject URLs capable of reaching the host or a private/internal network."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ExtractionFailed("That recipe URL is not valid.") from exc

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ExtractionFailed("Recipe links must use http:// or https://.")
    if parsed.username or parsed.password:
        raise ExtractionFailed("Recipe links cannot contain a username or password.")
    if port and port not in {80, 443}:
        raise ExtractionFailed("Recipe links must use the standard web ports (80 or 443).")

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise ExtractionFailed("That address is not a public recipe website.")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                port or (443 if parsed.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ExtractionFailed("That recipe website could not be found.") from exc
        addresses = list({info[4][0] for info in infos})

    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ExtractionFailed("That address is not a public recipe website.")
    return url


async def fetch_page(url: str) -> str:
    """Fetch a bounded public HTML page, validating every redirect target."""
    current = url
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=2)
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=False, limits=limits) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _validate_public_url(current)
            async with client.stream("GET", current, headers=_BROWSER_HEADERS) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise ExtractionFailed("The recipe website returned an invalid redirect.")
                    current = urljoin(current, location)
                    continue

                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "").lower()
                if content_type and not any(
                    kind in content_type
                    for kind in ("text/html", "application/xhtml+xml", "application/ld+json")
                ):
                    raise ExtractionFailed("That link did not return a web page.")
                try:
                    declared_size = int(resp.headers.get("content-length", "0"))
                except ValueError:
                    declared_size = 0
                if declared_size > MAX_FETCH_BYTES:
                    raise ExtractionFailed("That recipe page is too large to import safely.")

                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_FETCH_BYTES:
                        raise ExtractionFailed("That recipe page is too large to import safely.")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                encoding = resp.encoding or "utf-8"
                return raw.decode(encoding, errors="replace")

        raise ExtractionFailed("The recipe website redirected too many times.")


_EXTRACT_SYSTEM = """You extract a recipe's ingredient list from web page text.

Return ONLY JSON:
{"title": str, "yield": str, "ingredients": [str, ...], "instructions": str}

Rules:
- `ingredients` must contain ONLY ingredient lines, each copied VERBATIM from \
the page text. Never paraphrase, never invent, never include prep steps, \
equipment, headings, ads, or commentary.
- If the page does not contain a recipe with an ingredient list, return \
exactly {"extraction_failed": true} and nothing else.
- `instructions` is a short excerpt of the cooking method (max ~1500 chars), \
used only to detect cooking transformations. Empty string if absent."""


async def extract_with_llm(page_text: str) -> Optional[dict]:
    """Fallback extraction for pages with no structured data."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    payload = {
        "model": settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 2000,
        # No `temperature`: it is deprecated for claude-sonnet-5 and passing it
        # at all returns 400. The spec asks for temperature 0; the model does
        # not accept the parameter, so determinism rests on its default plus the
        # strict JSON contract and the hallucination check below.
        "system": _EXTRACT_SYSTEM,
        "messages": [{"role": "user", "content": page_text[:18000]}],
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = _json_from(_response_text(r.json()))
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    if not data or data.get("extraction_failed"):
        return None
    ingredients = [str(i).strip() for i in (data.get("ingredients") or []) if str(i).strip()]
    if len(ingredients) < 2:
        return None
    return {
        "title":        str(data.get("title") or "Imported recipe"),
        "yield":        str(data.get("yield") or ""),
        "ingredients":  ingredients,
        "instructions": str(data.get("instructions") or "")[:4000],
        "method":       "llm",
    }


async def extract_recipe(url: Optional[str] = None, text: Optional[str] = None) -> dict:
    """
    Get a recipe from a URL or from pasted text.

    Pasted text is a first-class entry point, not only a fallback — people copy
    recipes out of cookbooks, messages, and paywalled sites.
    """
    if text and text.strip():
        lines = [l.strip(" \t-•*") for l in text.splitlines()]
        lines = [l for l in lines if l]
        if len(lines) >= 2:
            return {
                "title": "Pasted recipe", "yield": "", "ingredients": lines,
                "instructions": "", "method": "pasted",
            }
        raise ExtractionFailed("Not enough ingredient lines in the pasted text.")

    if not url:
        raise ExtractionFailed("Provide a recipe URL or paste the ingredients.")

    try:
        html = await fetch_page(url)
    except httpx.HTTPError as exc:
        raise ExtractionFailed(f"Couldn't load that page ({type(exc).__name__}).") from exc

    structured = extract_structured(html)
    if structured:
        structured["source_url"] = url
        return structured

    stripper = _TextExtractor()
    stripper.feed(html)
    llm = await extract_with_llm(stripper.get_text(max_chars=18000))
    if llm:
        llm["source_url"] = url
        return llm

    raise ExtractionFailed("Couldn't find a recipe on that page.")


# ── Stage 2: parse each ingredient line ──────────────────────────────────────

_PARSE_SYSTEM = """You convert raw recipe ingredient lines into structured JSON.
You are a parser. You never produce nutrition information of any kind.

Return ONLY a JSON array, one object per input line, in the same order:
{"raw": str, "quantity": number|null, "unit": str|null, "name": str,
 "prep_state": "raw"|"cooked"|"dry"|"drained"|"canned"|null,
 "flags": [str], "confidence": number}

Rules:
- `raw` must be the input line copied exactly.
- Normalise unicode fractions (½ → 0.5, 1½ → 1.5) and mixed numbers.
- Ranges ("2-3 tbsp", "1½–2 tbsp") → the midpoint, plus the flag "range".
- Count quantities ("2 large eggs") → quantity 2, unit "large" (the size word) \
or null if none given.
- `name` is the food alone, cleaned for database search: drop amounts, brand \
puffery and prep verbs that do not change the food's identity ("finely \
chopped" → drop), but KEEP words that change its nutrition ("cooked", "dry", \
"canned", "drained", "skinless", "low-fat").
- `prep_state` captures how the food is when measured. "2 cups cooked rice" is \
cooked; "1 cup rice" is dry. This matters more than anything else you decide: \
cooked and dry rice differ about threefold per cup.
- Flags, only when genuinely present:
  "optional"    — "optional", "if desired", "for serving"
  "garnish"     — "to garnish", "for garnish"
  "to_taste"    — "to taste", "as needed", "season with"
  "partial_use" — "divided", "reserve half", "plus more for greasing", or a \
marinade/brine the instructions discard
  "sub_recipe"  — refers to another recipe ("1 batch pizza dough (see recipe)")
  "range"       — a quantity range was given
- `confidence` 0-1: how sure you are of quantity, unit and food identity.
- Never invent a line that was not in the input. Never merge or split lines."""


def _json_from(raw: str) -> Optional[Any]:
    """Pull the first JSON object/array out of a model reply."""
    if not raw:
        return None
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = raw.find(opener), raw.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _is_hallucinated(parsed_raw: str, sources: list[str]) -> bool:
    """
    Spec guardrail: every parsed line must correspond to real source text.

    Compared on normalised token overlap rather than exact substring, because
    the model legitimately fixes unicode fractions and whitespace in `raw`.
    """
    p = set(_normalise(parsed_raw).split())
    if not p:
        return True
    for s in sources:
        toks = set(_normalise(s).split())
        if toks and len(p & toks) / len(p) >= 0.6:
            return False
    return True


async def parse_ingredient_lines(lines: list[str], instructions: str = "") -> list[dict]:
    """
    One batched model call for the whole ingredient list — not one per line,
    which would multiply both latency and cost by the length of the recipe.
    """
    if not lines:
        return []
    if not settings.ANTHROPIC_API_KEY:
        raise ExtractionFailed("Ingredient parsing is unavailable (no API key configured).")

    user = "Ingredient lines:\n" + "\n".join(f"{i+1}. {l}" for i, l in enumerate(lines))
    if instructions:
        user += (
            "\n\nCooking instructions (context only — use them to spot discarded "
            "marinades and partial use; do not add ingredients from them):\n"
            + instructions[:1500]
        )

    payload = {
        "model": settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 4000,
        "system": _PARSE_SYSTEM,   # no `temperature` — deprecated for sonnet-5
        
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        r.raise_for_status()
        parsed = _json_from(_response_text(r.json()))

    if not isinstance(parsed, list):
        raise ExtractionFailed("Could not parse the ingredient list.")

    out: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("raw") or "").strip()
        if _is_hallucinated(raw, lines):
            continue                      # drop rather than trust
        flags = [str(f) for f in (item.get("flags") or []) if f]
        try:
            qty = float(item["quantity"]) if item.get("quantity") is not None else None
        except (TypeError, ValueError):
            qty = None
        try:
            conf = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5
        out.append({
            "raw":        raw,
            "quantity":   qty,
            "unit":       (str(item["unit"]).strip() if item.get("unit") else None),
            "name":       str(item.get("name") or raw).strip(),
            "prep_state": (str(item["prep_state"]).strip().lower() if item.get("prep_state") else None),
            "flags":      flags,
            "confidence": conf,
        })
    if not out:
        raise ExtractionFailed("Could not parse the ingredient list.")
    return out
