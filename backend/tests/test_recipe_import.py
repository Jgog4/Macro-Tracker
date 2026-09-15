import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.schemas.recipe_import import SaveLine, SaveRequest
from app.services.recipe_import import (
    _apply_culinary_default, _ingredient_choices, _recover_stated_unit,
)
from app.services.recipe_math import compute_recipe_totals
from app.services.units import to_grams
from app.services.recipe_import import ExtractionFailed, _validate_public_url
from app.services.ingredient_identity import form_penalty, is_unsafe_automatic_match


class RecipeURLSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_loopback_and_private_addresses(self):
        for url in (
            "http://127.0.0.1/recipe",
            "http://10.0.0.8/recipe",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]/recipe",
            "http://localhost/recipe",
        ):
            with self.subTest(url=url), self.assertRaises(ExtractionFailed):
                await _validate_public_url(url)

    async def test_accepts_public_standard_web_url(self):
        self.assertEqual(
            await _validate_public_url("https://8.8.8.8/recipe"),
            "https://8.8.8.8/recipe",
        )

    async def test_rejects_credentials_and_nonstandard_ports(self):
        for url in ("https://user:pass@example.com/recipe", "https://8.8.8.8:8443/recipe"):
            with self.subTest(url=url), self.assertRaises(ExtractionFailed):
                await _validate_public_url(url)

    async def test_rejects_hostname_when_dns_returns_private_address(self):
        private_answer = [
            (2, 1, 6, "", ("10.2.3.4", 443)),
        ]
        with patch("app.services.recipe_import.socket.getaddrinfo", return_value=private_answer):
            with self.assertRaises(ExtractionFailed):
                await _validate_public_url("https://recipes.example/meal")


class RecipeImportValidationTests(unittest.TestCase):
    def test_rejects_nonpositive_or_nonfinite_weights(self):
        for grams in (0, -1, float("inf"), float("nan")):
            with self.subTest(grams=grams), self.assertRaises(ValidationError):
                SaveLine(
                    name="Flour",
                    ingredient_id="123e4567-e89b-42d3-a456-426614174000",
                    grams=grams,
                )

    def test_rejects_blank_title_and_non_web_source(self):
        line = SaveLine(
            name="Flour",
            ingredient_id="123e4567-e89b-42d3-a456-426614174000",
            grams=100,
        )
        with self.assertRaises(ValidationError):
            SaveRequest(title="   ", lines=[line])
        with self.assertRaises(ValidationError):
            SaveRequest(title="Bread", source_url="javascript:alert(1)", lines=[line])

    def test_preview_requires_exactly_one_bounded_source(self):
        from app.schemas.recipe_import import PreviewRequest

        with self.assertRaises(ValidationError):
            PreviewRequest()
        with self.assertRaises(ValidationError):
            PreviewRequest(url="https://example.com", text="1 cup flour\n1 egg")
        with self.assertRaises(ValidationError):
            PreviewRequest(text="\n".join(f"ingredient {i}" for i in range(251)))


class RecipeCookingAdjustmentTests(unittest.TestCase):
    def test_fat_retention_changes_saved_totals(self):
        beef = SimpleNamespace(
            serving_size_g=100.0,
            calories=250.0,
            protein_g=20.0,
            fat_g=18.0,
            carbs_g=0.0,
            sodium_mg=70.0,
            cholesterol_mg=80.0,
        )
        totals = compute_recipe_totals([(beef, 100.0, 0.5)])
        self.assertEqual(totals["fat_g"], 9.0)
        self.assertEqual(totals["calories"], 169.0)

    def test_default_retention_preserves_existing_recipe_math(self):
        oil = SimpleNamespace(
            serving_size_g=100.0,
            calories=884.0,
            protein_g=0.0,
            fat_g=100.0,
            carbs_g=0.0,
            sodium_mg=0.0,
            cholesterol_mg=0.0,
        )
        totals = compute_recipe_totals([(oil, 10.0)])
        self.assertEqual(totals["fat_g"], 10.0)
        self.assertEqual(totals["calories"], 88.4)


class RecipeUnitRecoveryTests(unittest.TestCase):
    def test_recovers_tablespoon_omitted_by_parser(self):
        self.assertEqual(_recover_stated_unit("3 tbsp tomato paste", None), "tbsp")

    def test_tomato_paste_volume_never_uses_whole_tomato_weight(self):
        grams, method = to_grams(3, "tbsp", "tomato paste")
        self.assertEqual(method, "density")
        self.assertAlmostEqual(grams, 48.8, places=1)

    def test_dried_oregano_uses_light_volume_conversion(self):
        grams, method = to_grams(2, "tsp", "dried oregano")
        self.assertEqual(method, "density")
        self.assertAlmostEqual(grams, 2.0, places=1)

    def test_grated_parmesan_cup_converts_without_manual_weight(self):
        grams, method = to_grams(0.5, "cup", "parmesan cheese, grated")
        self.assertEqual(method, "density")
        self.assertAlmostEqual(grams, 50.0, places=1)


class RecipeChoiceTests(unittest.TestCase):
    def test_chooses_primary_and_preserves_meat_alternative(self):
        primary, alternatives = _ingredient_choices("ground beef or lamb (mince) ((Note 1))")
        self.assertEqual(primary, "ground beef")
        self.assertEqual(alternatives, ["lamb"])

    def test_completes_shared_noun_choices(self):
        primary, alternatives = _ingredient_choices("red or yellow onion")
        self.assertEqual(primary, "red onion")
        self.assertEqual(alternatives, ["yellow onion"])


class IngredientIdentityTests(unittest.TestCase):
    def test_bare_recipe_pepper_means_black_pepper(self):
        self.assertEqual(_apply_culinary_default("pepper"), "black pepper")
        grams, method = to_grams(0.25, "tsp", "black pepper")
        self.assertEqual(method, "density")
        self.assertAlmostEqual(grams, 0.6, places=1)

    def test_plain_milk_rejects_dry_milk_but_accepts_whole_milk(self):
        self.assertGreater(form_penalty(["milk"], "Milk, dry whole"), 0)
        self.assertTrue(is_unsafe_automatic_match(["milk"], "Milk, dry whole"))
        self.assertEqual(form_penalty(["milk"], "Milk, whole, UHT"), 0)

    def test_explicit_dry_milk_is_not_rejected(self):
        self.assertEqual(form_penalty(["milk", "dry"], "Milk, dry whole"), 0)
        self.assertFalse(is_unsafe_automatic_match(["milk", "dry"], "Milk, dry whole"))

    def test_plain_beef_does_not_auto_match_broth(self):
        self.assertTrue(is_unsafe_automatic_match(["beef"], "Soup, broth, beef, ready-to-serve"))


if __name__ == "__main__":
    unittest.main()
