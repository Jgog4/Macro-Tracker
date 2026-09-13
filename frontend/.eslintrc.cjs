/* Minimal lint gate.
 *
 * Purpose is narrow and deliberate: catch identifiers that are used but never
 * imported or declared. Vite/esbuild happily bundle those — the bundle builds,
 * the page renders, and the call only explodes at runtime inside an event
 * handler, where nothing surfaces it. That is exactly how a recipe ingredient's
 * weight silently stopped recalculating: `decimalOnly` was used in three places
 * in RecipeBuilderModal but had been dropped from its import line.
 *
 * Style rules are intentionally left off so this stays a correctness gate that
 * never fails a deploy for cosmetic reasons.
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  rules: {
    "no-undef": "error",
  },
  ignorePatterns: ["dist/", "node_modules/"],
};
