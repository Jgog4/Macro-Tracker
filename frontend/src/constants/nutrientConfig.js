/**
 * Shared nutrient configuration — RDV targets and group definitions.
 * Used by MicronutrientPanel (daily totals) and FoodDetailModal (per-food view).
 *
 * RDV = Reference Daily Value (adult male, FDA/NIH guidelines)
 */

// ── Reference daily values ─────────────────────────────────────────────────
export const RDV = {
  // Vitamins
  vitamin_a_mcg:       900,
  vitamin_c_mg:        90,
  vitamin_d_mcg:       20,
  vitamin_e_mg:        15,
  vitamin_k_mcg:       120,
  thiamine_mg:         1.2,
  riboflavin_mg:       1.3,
  niacin_mg:           16,
  pantothenic_acid_mg: 5,
  pyridoxine_mg:       1.7,
  cobalamin_mcg:       2.4,
  biotin_mcg:          30,
  folate_mcg:          400,
  choline_mg:          550,
  // Minerals
  calcium_mg:    1000,
  iron_mg:       8,
  magnesium_mg:  420,
  phosphorus_mg: 700,
  potassium_mg:  4700,
  zinc_mg:       11,
  copper_mg:     0.9,
  manganese_mg:  2.3,
  selenium_mcg:  55,
  chromium_mcg:  35,
  iodine_mcg:    150,
  molybdenum_mcg:45,
  fluoride_mg:   4,
  // Amino acids — rough per-kg adult estimate (70 kg)
  histidine_g:     1.05,
  isoleucine_g:    1.40,
  leucine_g:       2.73,
  lysine_g:        2.10,
  methionine_g:    1.05,
  phenylalanine_g: 1.75,
  threonine_g:     1.05,
  tryptophan_g:    0.28,
  valine_g:        1.82,
  // Fatty acids
  omega3_ala_g: 1.6,
  omega3_epa_g: 0.25,
  omega3_dha_g: 0.25,
  // Carb details / other
  fiber_g:         38,
  soluble_fiber_g: 10,
  caffeine_mg:     400,
  alcohol_g:       14,
};

// ── Nutrient group definitions ─────────────────────────────────────────────
export const GROUPS = [
  {
    key:   "vitamins",
    label: "Vitamins",
    color: "#AF52DE",
    items: [
      { key: "vitamin_a_mcg",          label: "Vitamin A",          unit: "mcg" },
      { key: "vitamin_c_mg",           label: "Vitamin C",          unit: "mg"  },
      { key: "vitamin_d_mcg",          label: "Vitamin D",          unit: "mcg" },
      { key: "vitamin_e_mg",           label: "Vitamin E",          unit: "mg"  },
      { key: "vitamin_k_mcg",          label: "Vitamin K",          unit: "mcg" },
      { key: "thiamine_mg",            label: "B1 · Thiamine",      unit: "mg"  },
      { key: "riboflavin_mg",          label: "B2 · Riboflavin",    unit: "mg"  },
      { key: "niacin_mg",              label: "B3 · Niacin",        unit: "mg"  },
      { key: "pantothenic_acid_mg",    label: "B5 · Pantothenic",   unit: "mg"  },
      { key: "pyridoxine_mg",          label: "B6 · Pyridoxine",    unit: "mg"  },
      { key: "cobalamin_mcg",          label: "B12 · Cobalamin",    unit: "mcg" },
      { key: "biotin_mcg",             label: "Biotin",             unit: "mcg" },
      { key: "folate_mcg",             label: "Folate",             unit: "mcg" },
      { key: "choline_mg",             label: "Choline",            unit: "mg"  },
      { key: "retinol_mcg",            label: "Retinol",            unit: "mcg" },
      { key: "alpha_carotene_mcg",     label: "α-Carotene",         unit: "mcg" },
      { key: "beta_carotene_mcg",      label: "β-Carotene",         unit: "mcg" },
      { key: "beta_cryptoxanthin_mcg", label: "β-Cryptoxanthin",    unit: "mcg" },
      { key: "lutein_zeaxanthin_mcg",  label: "Lutein+Zeaxanthin",  unit: "mcg" },
      { key: "lycopene_mcg",           label: "Lycopene",           unit: "mcg" },
      { key: "beta_tocopherol_mg",     label: "β-Tocopherol",       unit: "mg"  },
      { key: "delta_tocopherol_mg",    label: "δ-Tocopherol",       unit: "mg"  },
      { key: "gamma_tocopherol_mg",    label: "γ-Tocopherol",       unit: "mg"  },
    ],
  },
  {
    key:   "minerals",
    label: "Minerals",
    color: "#FF9500",
    items: [
      { key: "calcium_mg",     label: "Calcium",    unit: "mg"  },
      { key: "iron_mg",        label: "Iron",       unit: "mg"  },
      { key: "magnesium_mg",   label: "Magnesium",  unit: "mg"  },
      { key: "phosphorus_mg",  label: "Phosphorus", unit: "mg"  },
      { key: "potassium_mg",   label: "Potassium",  unit: "mg"  },
      { key: "zinc_mg",        label: "Zinc",       unit: "mg"  },
      { key: "copper_mg",      label: "Copper",     unit: "mg"  },
      { key: "manganese_mg",   label: "Manganese",  unit: "mg"  },
      { key: "selenium_mcg",   label: "Selenium",   unit: "mcg" },
      { key: "chromium_mcg",   label: "Chromium",   unit: "mcg" },
      { key: "iodine_mcg",     label: "Iodine",     unit: "mcg" },
      { key: "molybdenum_mcg", label: "Molybdenum", unit: "mcg" },
      { key: "fluoride_mg",    label: "Fluoride",   unit: "mg"  },
    ],
  },
  {
    key:   "amino_acids",
    label: "Amino Acids",
    color: "#34C759",
    items: [
      { key: "alanine_g",        label: "Alanine",        unit: "g" },
      { key: "arginine_g",       label: "Arginine",       unit: "g" },
      { key: "aspartic_acid_g",  label: "Aspartic acid",  unit: "g" },
      { key: "cystine_g",        label: "Cystine",        unit: "g" },
      { key: "glutamic_acid_g",  label: "Glutamic acid",  unit: "g" },
      { key: "glycine_g",        label: "Glycine",        unit: "g" },
      { key: "histidine_g",      label: "Histidine",      unit: "g" },
      { key: "hydroxyproline_g", label: "Hydroxyproline", unit: "g" },
      { key: "isoleucine_g",     label: "Isoleucine",     unit: "g" },
      { key: "leucine_g",        label: "Leucine",        unit: "g" },
      { key: "lysine_g",         label: "Lysine",         unit: "g" },
      { key: "methionine_g",     label: "Methionine",     unit: "g" },
      { key: "phenylalanine_g",  label: "Phenylalanine",  unit: "g" },
      { key: "proline_g",        label: "Proline",        unit: "g" },
      { key: "serine_g",         label: "Serine",         unit: "g" },
      { key: "threonine_g",      label: "Threonine",      unit: "g" },
      { key: "tryptophan_g",     label: "Tryptophan",     unit: "g" },
      { key: "tyrosine_g",       label: "Tyrosine",       unit: "g" },
      { key: "valine_g",         label: "Valine",         unit: "g" },
    ],
  },
  {
    key:   "fatty_acids",
    label: "Fatty Acids",
    color: "#FF3B30",
    items: [
      { key: "monounsaturated_fat_g", label: "Monounsaturated", unit: "g"  },
      { key: "polyunsaturated_fat_g", label: "Polyunsaturated", unit: "g"  },
      { key: "omega3_ala_g",          label: "Omega-3 ALA",     unit: "g"  },
      { key: "omega3_epa_g",          label: "Omega-3 EPA",     unit: "g"  },
      { key: "omega3_dha_g",          label: "Omega-3 DHA",     unit: "g"  },
      { key: "omega6_la_g",           label: "Omega-6 LA",      unit: "g"  },
      { key: "omega6_aa_g",           label: "Omega-6 AA",      unit: "g"  },
      { key: "phytosterol_mg",        label: "Phytosterols",    unit: "mg" },
    ],
  },
  {
    key:   "carb_details",
    label: "Carb Details & Other",
    color: "#007AFF",
    items: [
      { key: "soluble_fiber_g",        label: "Soluble Fiber",    unit: "g"  },
      { key: "insoluble_fiber_g",      label: "Insoluble Fiber",  unit: "g"  },
      { key: "fructose_g",             label: "Fructose",         unit: "g"  },
      { key: "galactose_g",            label: "Galactose",        unit: "g"  },
      { key: "glucose_g",              label: "Glucose",          unit: "g"  },
      { key: "lactose_g",              label: "Lactose",          unit: "g"  },
      { key: "maltose_g",              label: "Maltose",          unit: "g"  },
      { key: "sucrose_g",              label: "Sucrose",          unit: "g"  },
      { key: "oxalate_mg",             label: "Oxalate",          unit: "mg" },
      { key: "phytate_mg",             label: "Phytate",          unit: "mg" },
      { key: "caffeine_mg",            label: "Caffeine",         unit: "mg" },
      { key: "water_g",                label: "Water",            unit: "g"  },
      { key: "ash_g",                  label: "Ash",              unit: "g"  },
      { key: "alcohol_g",              label: "Alcohol",          unit: "g"  },
      { key: "beta_hydroxybutyrate_g", label: "β-Hydroxybutyrate",unit: "g"  },
    ],
  },
];

// ── Value formatter (shared) ───────────────────────────────────────────────
export function formatNutrientValue(v) {
  if (v == null) return "—";
  if (v < 0.1)   return v.toFixed(3);
  if (v < 10)    return v.toFixed(2);
  if (v < 100)   return v.toFixed(1);
  return v.toFixed(0);
}
