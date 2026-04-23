#!/usr/bin/env python3
"""
import_restaurants.py — zero external dependencies (stdlib only)
────────────────────────────────────────────────────────────────
Imports restaurant menu items from three sources into the Macro Tracker DB:

  • Cactus Club Cafe  (Oct 2025 nutrition PDF)
  • Chipotle          (CA Nutrition Facts, 2024)
  • Pokerrito         (April 2026 nutrition page)

All items are stored with source="restaurant" and brand=<restaurant name>.
Macros are stored as-is per the official serving size listed.

Micronutrient estimation
────────────────────────
Restaurant PDFs rarely include micronutrients. For fish and seafood items,
omega-3 EPA/DHA, selenium, vitamin D, and B12 are estimated from USDA
FoodData Central per-100g values, scaled to the item's known protein content.

  Per-100g cooked estimates (USDA FoodData Central):
  ┌──────────────────────┬──────────┬──────────┬────────────┬──────────────┬────────────┐
  │ Fish                 │ EPA (g)  │ DHA (g)  │ Se (mcg)   │ Vit D (mcg)  │ B12 (mcg)  │
  ├──────────────────────┼──────────┼──────────┼────────────┼──────────────┼────────────┤
  │ Yellowfin/Ahi Tuna   │  0.010   │  0.220   │  108       │   2.0        │  0.5       │
  │ Albacore Tuna        │  0.330   │  1.000   │   91       │   2.2        │  2.2       │
  │ Sockeye Salmon       │  0.530   │  0.740   │   32       │  10.9        │  3.2       │
  │ Atlantic Salmon      │  0.580   │  1.430   │   36       │  13.1        │  2.4       │
  │ Shrimp               │  0.120   │  0.130   │   38       │   0.6        │  1.1       │
  │ Scallop              │  0.080   │  0.140   │   18       │   0.2        │  1.4       │
  │ Octopus              │  0.100   │  0.200   │   44       │   0.0        │ 36.0       │
  │ Halibut              │  0.060   │  0.380   │   46       │   4.4        │  1.2       │
  │ Prawn/Lobster        │  0.120   │  0.130   │   38       │   0.6        │  1.1       │
  └──────────────────────┴──────────┴──────────┴────────────┴──────────────┴────────────┘

  Protein density used to back-calculate fish weight from dish protein:
    fish_g = dish_protein_g / protein_density_per_100g * 100
    nutrient = per_100g_value * fish_g / 100

Usage
─────
  API_URL=https://<app>.up.railway.app python3 scripts/import_restaurants.py
  API_URL=http://localhost:8000 python3 scripts/import_restaurants.py
  python3 scripts/import_restaurants.py --dry-run
  python3 scripts/import_restaurants.py --overwrite
  python3 scripts/import_restaurants.py --brand "Cactus Club Cafe"
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

# ── USDA per-100g cooked estimates for seafood micronutrients ─────────────────
#  (epa_g, dha_g, selenium_mcg, vitamin_d_mcg, cobalamin_mcg, protein_per_100g)
SEAFOOD_MICRO = {
    "ahi_tuna":       (0.010, 0.220, 108, 2.0,  0.5,  29),
    "albacore_tuna":  (0.330, 1.000,  91, 2.2,  2.2,  28),
    "sockeye_salmon": (0.530, 0.740,  32, 10.9, 3.2,  22),
    "atlantic_salmon":(0.580, 1.430,  36, 13.1, 2.4,  20),
    "shrimp":         (0.120, 0.130,  38, 0.6,  1.1,  24),
    "scallop":        (0.080, 0.140,  18, 0.2,  1.4,  17),
    "octopus":        (0.100, 0.200,  44, 0.0, 36.0,  15),
    "halibut":        (0.060, 0.380,  46, 4.4,  1.2,  23),
    "prawn":          (0.120, 0.130,  38, 0.6,  1.1,  20),
    "salmon_generic": (0.530, 0.740,  34, 11.0, 2.8,  21),
    "tuna_generic":   (0.010, 0.220, 108, 2.0,  0.5,  29),
}


def estimate_seafood_micros(profile_key: str, dish_protein_g: float) -> dict:
    """
    Given a seafood profile and the total protein in the dish,
    back-calculate the approximate fish weight and scale the micronutrients.
    Returns a dict of nutrient fields to add to the payload.
    """
    if profile_key not in SEAFOOD_MICRO:
        return {}
    epa, dha, sel, vitd, b12, prot_density = SEAFOOD_MICRO[profile_key]
    # Estimate fish weight from protein content
    fish_g = (dish_protein_g / prot_density) * 100
    factor = fish_g / 100.0
    return {
        "omega3_epa_g":  round(epa  * factor, 3),
        "omega3_dha_g":  round(dha  * factor, 3),
        "selenium_mcg":  round(sel  * factor, 1),
        "vitamin_d_mcg": round(vitd * factor, 2),
        "cobalamin_mcg": round(b12  * factor, 2),
    }


# ── Helper: build a base payload ─────────────────────────────────────────────
def item(name, brand, serving_g, cal, fat, sat_fat, trans_fat,
         chol_mg, sodium_mg, carbs, fiber, sugar, protein,
         seafood_profile=None, **extra):
    """Return a dict ready to POST to /api/v1/foods/."""
    payload = {
        "name":              name,
        "source":            "restaurant",
        "brand":             brand,
        "serving_size_g":    float(serving_g),
        "serving_size_desc": f"{serving_g} g",
        "calories":          float(cal),
        "fat_g":             float(fat),
        "sat_fat_g":         float(sat_fat),
        "trans_fat_g":       float(trans_fat),
        "cholesterol_mg":    float(chol_mg),
        "sodium_mg":         float(sodium_mg),
        "carbs_g":           float(carbs),
        "fiber_g":           float(fiber),
        "sugar_g":           float(sugar),
        "protein_g":         float(protein),
    }
    if seafood_profile:
        payload.update(estimate_seafood_micros(seafood_profile, float(protein)))
    payload.update(extra)
    return payload


# ═══════════════════════════════════════════════════════════════════════════════
# RESTAURANT DATA
# ═══════════════════════════════════════════════════════════════════════════════

CC = "Cactus Club Cafe"
CH = "Chipotle"
PK = "Pokerrito"

RESTAURANT_ITEMS = [

    # ──────────────────────────────────────────────────────────────────────────
    # CACTUS CLUB CAFE  (Oct 2025 PDF, all categories)
    # Columns: name, brand, serving_g, cal, fat, sat, trans, chol, sodium,
    #          carbs, fiber, sugar, protein [, seafood_profile]
    # ──────────────────────────────────────────────────────────────────────────

    # START + SHARE
    item("Ravioli & Prawn Trio",               CC, 199, 560, 45, 22, 1.5, 235,1100, 19, 1, 3,  17, "prawn"),
    item("Individual Ravioli & Prawn",         CC,  66, 190, 15,  7, 0.5,  80, 370,  6, 0, 1,   6, "prawn"),
    item("Chicken Wings",                      CC, 259, 850, 55, 15, 0.5, 350, 330,  0, 0, 0,  83),
    item("Chicken Wings — Hot Sauce",          CC,  75,  15,0.4,  0,   0,   0,2520,  3, 1, 1,   1),
    item("Chicken Wings — Salt & Pepper",      CC, 260, 860, 55, 16, 0.5, 350, 530,  0, 0, 0,  83),
    item("Creamy Parmesan Dip (sm)",           CC,  30, 170, 20,  4,   0,  20,  80,  1, 0, 0,   1),
    item("Crispy Yam Fries",                   CC, 292, 840, 48,3.5, 0.2,   0,1500, 98,11,29,   5),
    item("Garlic Mayo",                        CC,  45, 290, 35,  6,   0,  30, 150,  1, 0, 0, 0.1),
    item("Mini Burgers (trio)",                CC, 356, 980, 67, 26,   1, 200,1110, 41, 4,24,  44),
    item("Individual Mini Burger",             CC, 119, 330, 22,  9, 0.3,  65, 370, 14, 1, 8,  15),
    item("Mini Crispy Chicken Sandwiches (trio)",CC,345,930, 65, 19,   1, 180,1680, 49, 4,26,  34),
    item("Individual Mini Crispy Chicken Sandwich",CC,115,310,22, 6, 0.3,  60, 560, 16, 1, 9,  11),
    item("Potato Skins",                       CC, 299,1050, 87, 25,   1, 110,1870, 39, 4, 3,  32),
    item("Szechuan Chicken Lettuce Wraps",     CC, 671,1320, 81, 10, 0.1, 145,1950,100, 6,39,  66),
    item("Szechuan Tofu Lettuce Wraps",        CC, 608,1160, 92, 11, 0.1,  20,1870, 73, 6,38,  33),
    item("Creole Fries 12oz",                  CC, 289, 980, 81, 13, 0.5,  45,1250, 64, 6, 3,   7),
    item("Creole Fries 8oz",                   CC, 209, 760, 67, 11, 0.4,  45, 910, 43, 4, 2,   5),
    item("Creole Fries 4oz",                   CC, 129, 530, 52,  9, 0.2,  40, 600, 22, 2, 1,   3),
    item("Truffle Fries",                      CC, 249, 670, 47,  5, 0.2,  10,2480, 60, 5, 3,   9),
    item("Wagyu Beef Carpaccio",               CC, 297,1090, 89, 31,   2, 135,1890, 56, 4, 3,  25),
    item("Tuna Stack",                         CC, 298, 470, 28,3.5,   0,  35,1150, 35, 7, 8,  22, "ahi_tuna"),
    item("Hot Chicken & Pickles",              CC, 277, 790, 39,  4, 0.1, 130,1380, 56, 2,14,  51),
    item("Creamy Parmesan Dip",                CC,  45, 250, 29,  6,   0,  25, 120,  1, 0, 1,   2),
    item("Avocado Dip",                        CC, 217, 390, 25,  5, 0.1,  15,1050, 39, 9, 2,   9),
    item("Chili Citrus Calamari",              CC, 254, 590, 30,3.5, 0.1, 420, 740, 46, 2, 2,  34),
    item("Szechuan Beans",                     CC, 285, 390, 23,  2, 0.1,   0,1430, 42, 8,17,   9),
    item("Creole Crab & Spinach Dip",          CC, 343, 960, 60, 31, 1.5, 175,1370, 80, 4,15,  30),
    item("Warm Pull-Apart Bread",              CC, 173, 620, 32, 13,   1,  55, 900, 73, 3,14,  14),
    item("Scallop & Prawn Ceviche",            CC, 270, 510, 24,  2, 0.1, 130,1400, 47, 6, 5,  32, "scallop"),

    # HANDHELDS
    item("Chicken Tenders",                    CC, 283, 760, 38,  4, 0.1, 260,1360, 54, 2, 1,  51),
    item("Chicken Tenders — Honey Mustard",    CC,  45, 260, 29,  5,   0,  25, 190,  5, 0, 4, 0.3),
    item("Chicken Tenders — Sea Salted Fries", CC, 154, 400, 26,  2, 0.1,   0, 830, 40, 3, 2,   5),
    item("Cajun Chicken Sandwich",             CC, 312, 810, 54, 17, 0.5, 155,1180, 43, 3, 9,  40),
    item("BBQ Chicken Club Sandwich",          CC, 328, 840, 52, 13, 0.3, 150,1590, 53, 4,17,  39),
    item("Crispy Chicken Sandwich",            CC, 430, 970, 60, 13, 0.3, 130,2180, 67, 4,17,  46),
    item("Pesto Chicken Quesadilla",           CC, 277, 840, 40, 16, 0.5, 120,1370, 73, 5,10,  52),
    item("Pesto Chicken Quesadilla — Honey Lime Dip",CC,30,140,16, 3,   0,  15, 150,  3, 0, 3, 0.3),
    item("Chicken Fajitas",                    CC, 856,1490, 72, 31,   2, 255,5590,125,14,21,  87),
    item("Baja Fish Tacos",                    CC, 330, 760, 36,  5,   0,  30,1430, 85, 6, 7,  24, "tuna_generic"),
    item("Chipotle Chicken Tacos",             CC, 409, 830, 41,  9,   0, 100,1820, 75, 8, 5,  41),

    # FRESH GREENS
    item("Kale Salad",                         CC, 277, 450, 32,  5, 0.1,  10,1020, 38, 9, 6,  10),
    item("Chicken Kale Salad",                 CC, 357, 580, 34,  5, 0.1,  75,1120, 38,10, 6,  35),
    item("Kale Dressing",                      CC,  45, 230, 24,2.5, 0.2,   5, 310,  1, 0, 1,   1),
    item("Side/Add Kale Salad",                CC,  82,  90,  5,  1,   0,   5, 220,  9, 2, 2,   3),
    item("Sherry Vinaigrette",                 CC,  30, 170, 18,1.5, 0.1,   0, 110,  1, 0, 1, 0.2),
    item("Starter Fresh Greens",               CC, 140, 150, 12,  3, 0.2,  10, 270,  5, 2, 3,   4),
    item("Lemongrass Chicken Salad",           CC, 417, 670, 33,  4, 0.1,  65, 850, 60, 7,15,  35),
    item("Lemongrass Prawn Salad",             CC, 411, 630, 32,  4, 0.1, 160,1430, 60, 7,15,  27, "prawn"),
    item("Lemongrass Noodle Salad w/ Chicken", CC, 447, 720, 16,2.5,   0,  65,1160,106, 7,22,  37),
    item("Lemongrass Noodle Salad w/ Tuna",    CC, 456, 690, 16,2.5,   0,  45,1210,103, 7,21,  34, "ahi_tuna"),
    item("Lemongrass Noodle Salad (no protein)",CC,356, 570, 13,  2,   0,   0, 870,103, 7,21,  12),
    item("Green Goddess Chicken Salad",        CC, 392, 490, 27,  6, 0.1, 285, 760, 16, 7, 6,  47),
    item("Green Goddess Salmon Salad",         CC, 404, 420, 27,  6, 0.1, 270, 860, 16, 7, 6,  32, "atlantic_salmon"),
    item("Green Goddess Veg Salad",            CC, 297, 290, 22,4.5, 0.1, 190, 440, 16, 7, 6,  11),
    item("Maple Mustard Vinaigrette",          CC,  30, 130, 12,  1, 0.1,   0, 340,  4, 0, 3, 0.3),
    item("Green Goddess Dressing",             CC,  10,  30,  3,  1,   0,   5,  25,  0, 0, 0, 0.4),

    # BOWLS
    item("Crispy Tofu Bowl",                   CC, 604, 900, 50,  6, 0.1,   0,1550, 87,10,25,  27),
    item("Teriyaki Chicken Rice Bowl",         CC, 691,1070, 49,  7, 0.2, 100,2640,121, 7,32,  42),
    item("Tuna Poke Bowl",                     CC, 577, 880, 50,  6, 0.3,  60,1890, 78,11,22,  31, "ahi_tuna"),
    item("The Med Bowl — Vegan",               CC, 444, 700, 35,  5, 0.1,   0,1900, 76, 8,12,  11),
    item("The Med Bowl — Falafel",             CC, 459, 680, 29,  6, 0.2,  15,1970, 79, 8,15,  14),
    item("The Med Bowl — Chicken",             CC, 548, 870, 40, 10, 0.4,  90,1880, 78, 8,16,  39),

    # SUSHI
    item("Prawn Crunch Roll",                  CC, 258, 560, 23,1.5, 0.1,  85,1350, 68, 4,16,  15, "prawn"),
    item("Salmon Aburi Sushi",                 CC, 268, 500, 22,  3,   0,  45,1170, 60, 4,14,  14, "atlantic_salmon"),
    item("Tuna Temaki",                        CC, 193, 340,  7,0.5, 0.1,  25, 960, 49, 2,11,  16, "ahi_tuna"),

    # BURGERS & HANDHELDS
    item("Cactus Burger",                      CC, 448,1280, 93, 28, 1.5, 225,1950, 48, 4, 9,  67),
    item("Bacon Cheddar Burger",               CC, 398,1170, 79, 27, 1.5, 215,2130, 48, 3,10,  64),
    item("HH Cheeseburger",                    CC, 230, 620, 34, 11, 0.5, 105, 910, 42, 0, 8,  34),
    item("Garden Burger",                      CC, 308, 660, 35, 11,   0,  40,2190, 68, 6,11,  21),
    item("Cheddar Bacon Burger",               CC, 378, 890, 50, 17, 0.2, 135,2020, 62, 3,20,  52),
    item("Cheddar Burger",                     CC, 403, 830, 45, 15,   1, 125,1640, 62, 3,20,  47),
    item("The Feenie Burger",                  CC, 537,1170, 80, 34, 1.5, 195,2030, 64, 4,22,  54),
    item("GardenBurger",                       CC, 359, 950, 64, 20,   1,  85,1600, 72, 6,13,  25),
    item("JD BBQ Burger",                      CC, 378, 910, 59, 15,   0, 110,1480, 56, 3,17,  39),
    item("Side Sea Salted Fries",              CC, 154, 400, 26,  2, 0.1,   0, 830, 40, 3, 2,   5),
    item("Side Truffle Fries",                 CC, 166, 450, 31,3.5, 0.2,   5,1490, 40, 3, 2,   6),
    item("Yam Fries",                          CC, 167, 480, 28,  2, 0.1,   0, 860, 56, 6,17,   3),
    item("Side Fresh Greens",                  CC,  78,  70,  6,1.5, 0.1,   5, 130,  3, 1, 1,   2),

    # MAINS
    item("Blackened Creole Chicken",           CC, 503, 800, 48, 22, 0.5, 220,1840, 42, 6, 3,  52),
    item("Butternut Squash Prawn Ravioli",     CC, 373, 920, 69, 33, 2.5, 440,1830, 40, 2, 6,  34, "prawn"),
    item("Butternut Squash Vegetarian Ravioli",CC, 254, 700, 55, 30,   2, 235, 870, 39, 2, 5,  14),
    item("Rigatoni Bolognese",                 CC, 465, 980, 43, 17, 0.5, 105,1950,111,14,21,  41),
    item("Spaghetti Portofino",                CC, 475,1060, 69, 31, 1.5, 295,1650, 73, 4, 6,  31),
    item("Pane Romano (Crostini)",             CC,  54, 180,  9,  5, 0.4,  20, 300, 20, 1, 1,   4),
    item("Grilled Salmon",                     CC, 475, 710, 46, 16, 0.4, 160,1750, 42, 6, 3,  35, "atlantic_salmon"),
    item("Grilled Dijon Salmon",               CC, 516, 720, 43, 20, 0.5, 180,2270, 47, 8, 5,  36, "atlantic_salmon"),
    item("Truffle Chicken",                    CC, 550,1400, 97, 24,   1, 295,2320, 50, 5, 4,  82),
    item("Halibut Main",                       CC, 408, 940, 83, 27, 1.5, 110,2000, 30, 4, 6,  16, "halibut"),
    item("Thai Red Curry + Chicken",           CC, 657,1020, 36, 19,   0,  65,1850,132, 6,13,  39),
    item("Thai Red Curry + Tofu",              CC, 683,1140, 55, 20, 0.1,   0,1590,129, 6,11,  28),

    # STEAKS
    item("8 oz Sirloin",                       CC, 169, 330, 14,  7, 0.5, 120, 190,  0, 0, 0,  47),
    item("7 oz AAA Filet",                     CC, 132, 320, 15,  8, 0.5, 110, 180,  0, 0, 0,  41),
    item("12 oz NY Striploin",                 CC, 240, 540, 24, 11,   1, 180, 230,  0, 0, 0,  76),
    item("7oz AAA Filet w/ Lobster, Veg & Potatoes",CC,578,860,48,26,1,240,1830,47,8,3,65),
    item("12oz NY Striploin w/ Lobster, Veg & Potatoes",CC,686,1090,56,29,1.5,305,1880,47,8,3,100),
    item("Truffle Mushroom Steak w/ Veg & Potatoes",CC,637,990,61,26,1,200,2710,48,8,6,64),
    item("8oz Sirloin w/ Brandy Peppercorn, Veg & Potatoes",CC,560,970,60,29,1,230,3200,45,7,3,61),
    item("12oz Sirloin w/ Brandy Peppercorn, Veg & Potatoes",CC,642,1130,67,32,1,285,3250,45,7,3,83),
    item("7oz AAA Filet w/ Brandy Peppercorn, Veg & Potatoes",CC,524,930,57,29,1,215,3190,45,7,3,55),
    item("14oz Ribeye w/ Brandy Peppercorn, Veg & Potatoes",CC,679,1460,99,46,2,315,3260,45,7,3,93),

    # ──────────────────────────────────────────────────────────────────────────
    # CHIPOTLE  (CA Nutrition Facts Paper Menu, Oct 2024)
    # All items are individual components for build-your-own meals.
    # Serving sizes are the standard scoop/portion as listed.
    # ──────────────────────────────────────────────────────────────────────────

    # Tortillas / bases
    item("Flour Tortilla (burrito)",           CH, 117, 320,  9,0.5,   0,   0, 600, 50, 3, 0,   8),
    item("Flour Tortilla (taco)",              CH,  32,  80,2.5,  0,   0,   0, 160, 13, 0, 0,   2),
    item("Crispy Corn Tortilla",               CH,  28,  70,  3,0.5,   0,   0,   0, 10, 1, 0,   1),

    # Rice
    item("Cilantro-Lime Brown Rice",           CH, 113, 210,  4,  1,   0,   0, 195, 40,2.5, 0,   4),
    item("Cilantro-Lime White Rice",           CH, 113, 210,  4,  1,   0,   0, 345, 40, 1, 0, 3.5),

    # Beans
    item("Black Beans",                        CH, 113, 130, 15,  0,   0,   0, 210, 22, 7, 0,   8),
    item("Pinto Beans",                        CH, 113, 130, 15,  0,   0,   0, 210, 22, 8, 1,   8),

    # Fajita veggies
    item("Fajita Vegetables",                  CH,  57,  20,0.5,  0,   0,   0, 150,  5, 1, 2,   1),

    # Proteins
    item("Barbacoa",                           CH, 113, 170,7.5,2.5, 0,  65, 530,  2, 0, 0,  24),
    item("Chicken",                            CH, 113,  80,  7,  3,   0, 125, 310,  0,0.5, 0,  32),
    item("Carnitas",                           CH, 113, 210, 12,4.5,   0,  65, 450,  1, 0, 0,  23),
    item("Steak",                              CH, 113, 150,6.5,  2,   0,  80, 330,  1, 0, 0,  21),
    item("Sofritas",                           CH, 113, 150, 10,1.5,   0,   0, 590,  9,3.5, 4,   8),

    # Salsas
    item("Fresh Tomato Salsa",                 CH, 113,  25,  0,  0,   0,   0, 550,  4, 1, 0,   0),
    item("Roasted Chili-Corn Salsa",           CH,  85,  80, 15,  0,   0,   0, 330, 16, 3, 4,   3),
    item("Tomatillo-Green Chili Salsa",        CH,  57,  15,  0,  0,   0,   0, 255,  4,0.5, 0,   0),
    item("Tomatillo-Red Chili Salsa",          CH,  28,  30,  0,  0,   0,   0, 500,  4,0.5, 0,   0),

    # Extras
    item("Sour Cream",                         CH,  57,  90,4.5,  3,   0,  25,  45,  3, 0, 2,   1),
    item("Cheese",                             CH,  28, 100,  8,  5,   0,  25, 200,  0, 0, 0,   6),
    item("Romaine Lettuce",                    CH,  28,   5,  0,  0,   0,   0,   0,  1,0.5, 0,   0),
    item("Queso Blanco",                       CH, 113, 120,  9,  6,   0,  30, 490,  7, 0, 2,   5),
    item("Guacamole",                          CH, 226, 460, 44,  7,   0,   0, 740, 16, 8, 2,   4),
    item("Chips",                              CH, 170, 780, 38,  5,   0,   0, 590, 93, 7, 0,  11),

    # ──────────────────────────────────────────────────────────────────────────
    # POKERRITO  (April 2026 nutrition info page)
    # Customizable poke bowls — individual components.
    # Macro values based on official PDF + USDA estimates for seafood.
    # ──────────────────────────────────────────────────────────────────────────

    # Bases  (serving_g, cal, fat, sat, trans, chol, sodium, carbs, fiber, sugar, protein)
    item("Poke Bowl Base — White Rice (regular)",   PK, 220, 290, 0.4, 0.1, 0,  0,  10, 63, 0.5, 0,   5),
    item("Poke Bowl Base — White Rice (large)",     PK, 315, 415, 0.5, 0.1, 0,  0,  14, 91, 0.7, 0,   7),
    item("Poke Bowl Base — Brown Rice (regular)",   PK, 220, 250, 2.0, 0.4, 0,  0,  10, 52, 2.5, 0,   5),
    item("Poke Bowl Base — Brown Rice (large)",     PK, 315, 355, 2.5, 0.5, 0,  0,  14, 74, 3.5, 0,   7),
    item("Poke Bowl Base — Kale Noodle (regular)",  PK, 220, 180, 1.5, 0.2, 0,  0,  20, 38, 2.0, 2,   5),
    item("Poke Bowl Base — Kale Noodle (large)",    PK, 315, 255, 2.0, 0.3, 0,  0,  28, 54, 2.8, 3,   7),
    item("Pokerrito (black rice & seaweed wrap)",   PK, 230, 235, 0.5, 0.1, 0,  0, 200, 51, 1.0, 0,   6),
    item("Poke Salad Base — Romaine (regular)",     PK, 100,  20, 0.2, 0.0, 0,  0,  30,  4, 2.0, 2,   2),
    item("Poke Salad Base — Romaine (large)",       PK, 120,  25, 0.3, 0.0, 0,  0,  40,  5, 2.5, 2,   2),

    # Proteins — regular size (85g or stated serving)
    # col order: serving_g, cal, fat, sat, trans, chol_mg, sodium_mg, carbs, fiber, sugar, protein
    item("Marinated Ahi Tuna (regular)",    PK,  85, 100, 1.0, 0.3, 0,  33,  250, 1, 0, 0, 22, "ahi_tuna"),
    item("Marinated Ahi Tuna (large)",      PK, 145, 170, 1.5, 0.5, 0,  57,  425, 2, 0, 0, 37, "ahi_tuna"),
    item("Sockeye Salmon (regular)",        PK,  85, 118, 5.5, 1.0, 0,  50,   50, 0, 0, 0, 18, "sockeye_salmon"),
    item("Sockeye Salmon (large)",          PK, 145, 200, 9.5, 1.7, 0,  85,   85, 0, 0, 0, 30, "sockeye_salmon"),
    item("Albacore Tuna (regular)",         PK,  85, 145, 4.0, 0.8, 0,  40,  250, 0, 0, 0, 25, "albacore_tuna"),
    item("Albacore Tuna (large)",           PK, 145, 245, 7.0, 1.4, 0,  68,  425, 0, 0, 0, 42, "albacore_tuna"),
    item("Spicy Tuna (regular)",            PK,  90, 160, 8.0, 1.5, 0,  35,  350, 3, 0, 1, 20, "ahi_tuna"),
    item("Spicy Tuna (large)",              PK, 135, 240,12.0, 2.2, 0,  53,  525, 4, 0, 2, 30, "ahi_tuna"),
    item("Scallop — cooked (regular)",      PK,  40,  50, 0.5, 0.1, 0,  25,  125, 2, 0, 0,  9, "scallop"),
    item("Scallop — cooked (large)",        PK,  60,  75, 0.7, 0.1, 0,  37,  190, 3, 0, 0, 13, "scallop"),
    item("Shrimp — cooked (regular)",       PK,  40,  50, 0.7, 0.1, 0,  95,  220, 1, 0, 0,  9, "shrimp"),
    item("Shrimp — cooked (large)",         PK,  60,  75, 1.0, 0.2, 0, 143,  330, 1, 0, 0, 14, "shrimp"),
    item("Octopus (regular)",               PK,  40,  37, 0.5, 0.1, 0,  27,  200, 1, 0, 0,  7, "octopus"),
    item("Octopus (large)",                 PK,  70,  65, 0.8, 0.2, 0,  46,  350, 1, 0, 0, 11, "octopus"),
    item("Atlantic Salmon (regular)",       PK,  85, 156,10.0, 2.0, 0,  55,   50, 0, 0, 0, 17, "atlantic_salmon"),
    item("Atlantic Salmon (large)",         PK, 145, 265,17.0, 3.5, 0,  94,   85, 0, 0, 0, 29, "atlantic_salmon"),
    item("Tofu (regular)",                  PK,  80,  80, 4.5, 0.7, 0,   0,   10, 2, 0, 1,  9),
    item("Tofu (large)",                    PK, 120, 120, 7.0, 1.0, 0,   0,   15, 3, 0, 1, 13),
    item("Cooked Chicken (regular)",        PK,  80, 130, 3.0, 0.8, 0,  65,   70, 0, 0, 0, 25),
    item("Cooked Chicken (large)",          PK, 120, 195, 4.5, 1.2, 0,  98,  105, 0, 0, 0, 37),

    # Sauces
    item("Classic Mayo",                    PK,  18,  80, 8.0, 1.5, 0,   5,  80, 0, 0, 0, 0.2),
    item("Classic Signature Sauce (reg)",   PK,  22,  70, 7.0, 1.0, 0,   5, 110, 2, 0, 1, 0.5),
    item("Classic Signature Sauce (large)", PK,  33, 105,10.0, 1.5, 0,   8, 165, 3, 0, 2, 0.7),
    item("Spicy Signature Sauce (reg)",     PK,  22,  75, 7.5, 1.5, 0,   5, 120, 2, 0, 1, 0.5),
    item("Spicy Signature Sauce (large)",   PK,  33, 115,11.0, 2.5, 0,   8, 180, 3, 0, 2, 0.7),
    item("Creamy Mayo (regular)",           PK,  22,  75, 7.0, 1.0, 0,   5,  65, 2, 0, 1, 0.4),
    item("Creamy Mayo (large)",             PK,  33, 110,10.0, 1.5, 0,   8,  95, 3, 0, 2, 0.6),
    item("Sweet Chili (regular)",           PK,  18,  45, 0.0, 0.0, 0,   0,  40,11, 0,10,   0),
    item("Sweet Chili (large)",             PK,  25,  65, 0.0, 0.0, 0,   0,  55,16, 0,14,   0),
    item("Citrus Ponzu (regular)",          PK,  25,  10, 0.1, 0.0, 0,   0, 430, 2, 0, 1,   0),
    item("Citrus Ponzu (large)",            PK,  38,  15, 0.1, 0.0, 0,   0, 645, 3, 0, 2,   0),
]


# ── API helpers ───────────────────────────────────────────────────────────────

def api_get(path: str):
    req = urllib.request.Request(f"{API_URL}{path}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_post(path: str, data: dict):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        f"{API_URL}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def api_patch(path: str, data: dict):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        f"{API_URL}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="PATCH"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def get_existing_restaurant() -> dict:
    """Return {(brand, name): id} for all restaurant-source foods in the DB."""
    try:
        items = api_get("/api/v1/foods/?source=restaurant")
        return {(i["brand"], i["name"]): i["id"] for i in items}
    except Exception as e:
        print(f"  ⚠️  Could not fetch existing restaurant foods: {e}")
        return {}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",   action="store_true",
                        help="Print what would be imported without touching the DB")
    parser.add_argument("--overwrite", action="store_true",
                        help="PATCH existing items instead of skipping them")
    parser.add_argument("--brand",     type=str, default=None,
                        help="Only import items for this brand")
    args = parser.parse_args()

    payloads = RESTAURANT_ITEMS
    if args.brand:
        payloads = [p for p in payloads if p["brand"].lower() == args.brand.lower()]
        if not payloads:
            print(f"❌ No items found for brand '{args.brand}'")
            sys.exit(1)

    brands = sorted({p["brand"] for p in payloads})
    print(f"📋 {len(payloads)} items across {len(brands)} restaurant(s): {', '.join(brands)}")

    # Show which items have micronutrient estimates
    with_micros = sum(1 for p in payloads if "omega3_dha_g" in p)
    print(f"   {with_micros} items have estimated omega-3 / selenium / vitamin D data")

    if args.dry_run:
        print("\n── DRY RUN — first 12 payloads ──────────────────────────────────")
        for p in payloads[:12]:
            omega = f"  DHA={p['omega3_dha_g']:.2f}g" if "omega3_dha_g" in p else ""
            print(f"  [{p['brand'][:12]:12s}] {p['name'][:55]:55s}  "
                  f"cal={p['calories']:.0f}  P={p['protein_g']:.1f}g{omega}")
        print(f"\n  → would import {len(payloads)} items to {API_URL}")
        return

    # ── Live run ──
    print(f"\n🌐 API: {API_URL}")
    try:
        health = api_get("/health")
        print(f"   ✅ Connected ({health.get('status', 'ok')})")
    except Exception as e:
        print(f"   ❌ Cannot reach API: {e}")
        sys.exit(1)

    print("   Fetching existing restaurant foods …")
    existing = get_existing_restaurant()
    print(f"   {len(existing):,} already in DB")

    created = skipped = updated = errors = 0
    t0 = time.time()

    for i, payload in enumerate(payloads, 1):
        key  = (payload["brand"], payload["name"])

        if i % 50 == 0 or i == len(payloads):
            elapsed = time.time() - t0
            rate    = i / elapsed if elapsed else 1
            eta     = (len(payloads) - i) / rate
            print(f"   [{i:3d}/{len(payloads)}]  "
                  f"✅ {created}  🔄 {updated}  ⏭ {skipped}  ❌ {errors}  "
                  f"({rate:.0f}/s, ETA {eta:.0f}s)")

        if key in existing:
            if args.overwrite:
                status, _ = api_patch(f"/api/v1/foods/{existing[key]}", payload)
                if status == 200:
                    updated += 1
                else:
                    errors += 1
                    print(f"   ❌ PATCH {payload['name']!r}: HTTP {status}")
            else:
                skipped += 1
            continue

        status, body = api_post("/api/v1/foods/", payload)
        if status in (200, 201):
            created += 1
            if isinstance(body, dict):
                existing[key] = body.get("id", "")
        else:
            errors += 1
            print(f"   ❌ {payload['name']!r}: HTTP {status} — {body}")

    elapsed = time.time() - t0
    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   Created : {created:,}")
    print(f"   Updated : {updated:,}")
    print(f"   Skipped : {skipped:,}  (use --overwrite to replace)")
    print(f"   Errors  : {errors:,}")


if __name__ == "__main__":
    main()
