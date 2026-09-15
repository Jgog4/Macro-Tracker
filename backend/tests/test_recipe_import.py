import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.schemas.recipe_import import SaveLine, SaveRequest
from app.services.recipe_math import compute_recipe_totals
from app.services.recipe_import import ExtractionFailed, _validate_public_url


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


if __name__ == "__main__":
    unittest.main()
