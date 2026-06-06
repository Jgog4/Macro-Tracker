# Macro Tracker — Claude Code Context

## Project Overview
A mobile-first macro/nutrition tracking web app. Built as a single Railway deployment: FastAPI serves both the REST API and the production React build from `./static`.

- **Live URL**: deployed on Railway (check `railway.json` or `railway up` for details)
- **Stack**: React 18 + Vite + Tailwind CSS (frontend) · FastAPI + SQLAlchemy async + PostgreSQL (backend)
- **Deploy**: `bash deploy.sh "commit message"` — commits everything, pushes to GitHub, Railway auto-builds

---

## Repo Structure

```
Macro Tracker App/
├── deploy.sh                  # One-command deploy: git add -A + commit + push
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Root: tab routing, all global modals, bottom nav
│   │   ├── api/client.js      # Axios API client — all endpoint wrappers
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx      # "Today" tab — meals, macro summary, micronutrients
│   │   │   ├── LibraryPage.jsx    # Library tab — Recipes / My Foods / Restaurants
│   │   │   ├── ReportsPage.jsx    # Weekly/monthly reports modal
│   │   │   └── RecipesPage.jsx
│   │   └── components/
│   │       ├── AddFoodModal.jsx       # Search + log food (USDA, My Foods, Recipes)
│   │       ├── BarcodeModal.jsx       # Barcode scanner → log to diary
│   │       ├── VisionModal.jsx        # Camera/photo → AI reads nutrition label
│   │       ├── LogFoodModal.jsx       # Log a specific food from Library
│   │       ├── IngredientEditModal.jsx# Edit a food's nutrition data
│   │       ├── RecipeBuilderModal.jsx # Create/edit multi-ingredient recipes
│   │       ├── FoodDetailModal.jsx    # Full nutrition detail sheet
│   │       ├── MealSection.jsx        # Single meal card in Dashboard
│   │       ├── MacroSummaryCards.jsx  # Calorie/P/C/F summary
│   │       ├── MicronutrientPanel.jsx # Vitamin/mineral panel
│   │       ├── SuggestModal.jsx       # AI meal suggestions
│   │       ├── CopyMealModal.jsx      # Copy a meal to another date
│   │       ├── CustomMealModal.jsx    # Create a custom meal name
│   │       └── UrlFoodModal.jsx       # Add food from URL (AI estimates nutrition)
│   ├── tailwind.config.js     # Custom tokens: surface, accent-blue, muted, etc.
│   └── package.json
└── backend/
    └── app/
        ├── main.py            # FastAPI entry, lifespan (DB migrations), static serving
        ├── config.py          # Settings (DATABASE_URL, OPENAI_API_KEY, etc.)
        ├── database.py        # Async SQLAlchemy engine + session
        ├── models/models.py   # ORM models: Ingredient, MealLog, MealLogItem, Recipe, etc.
        ├── schemas/schemas.py # Pydantic schemas
        └── routers/
            ├── foods.py       # CRUD + USDA search/import + restaurant lookup
            ├── meals.py       # Log food, get day/today, update/delete items, copy meal, targets, micronutrients
            ├── recipes.py     # CRUD recipes
            ├── vision.py      # AI label scan, barcode lookup (Open Food Facts), URL/text nutrition
            ├── suggest.py     # AI meal suggestions
            └── api_keys.py    # API key management
```

---

## Key Architecture Patterns

### Frontend
- **Single-page app** — two main tabs ("Today" / "Library") in `App.jsx`, plus modals
- **Bottom nav**: Today | Library | [+] | Scan | Suggest
- **[+] action sheet** opens 4 options: Search Foods, Scan Barcode, Scan Label (camera), From Recipes
- **API calls** all go through `src/api/client.js` — never raw fetch/axios in components
- **Date navigation**: `currentDate` state in App.jsx; `dateStr = format(currentDate, "yyyy-MM-dd")`
- **Dashboard refresh**: `dashboardKey` state — increment to force remount after logging
- **Tailwind theme**: iOS-style light. Key tokens:
  - `bg-surface` (#F2F2F7) — page bg
  - `bg-surface-1` (#FFF) — cards
  - `bg-surface-2` (#F2F2F7) — inputs
  - `bg-surface-3` (#E5E5EA) — separators
  - `text-foreground` (#111827), `text-muted` (#8E8E93)
  - `bg-accent-blue` / `text-accent-blue` (#007AFF)
  - `accent-green` (#34C759), `accent-red` (#FF3B30), `accent-orange` (#FF9500)

### Backend
- **Async FastAPI** — all DB operations use `async with AsyncSession`
- **Migrations**: no Alembic — `main.py` lifespan runs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for every new column. Add new columns there.
- **Food sources**: `ingredient.source` controls visibility:
  - `"personal"` — imported from CSV (Cronometer export)
  - `"custom"` — camera-scanned or manually created
  - `"barcode"` — scanned via barcode but NOT saved to library
  - `"restaurant"` — restaurant brand items
  - `"usda"` — imported from USDA FoodData Central
- **Serving size scaling**: `base_g = serving_size_g or logged_quantity`. All macro display scales by `(logged_quantity / base_g)`.
- **Barcode**: `GET /api/v1/vision/barcode/{barcode}` — queries Open Food Facts (free, no key). Sodium stored as g/100g in OFF → multiply ×1000 for mg.
- **USDA**: `GET /api/v1/foods/usda/search?q=...` then `POST /api/v1/foods/usda/{fdc_id}/import`

---

## Database Models (key tables)

### `mt_ingredients` (Ingredient)
Core food item. Columns include:
- `id`, `name`, `source`, `brand`
- `serving_size_g`, `serving_size_desc`
- `calories`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `sugar_g`, `added_sugar_g`
- `sodium_mg`, `potassium_mg`, `calcium_mg`, `iron_mg`
- `vitamin_a_mcg`, `vitamin_c_mg`, `vitamin_d_mcg`, `vitamin_e_mg`, `vitamin_k_mcg`
- `thiamine_mg`, `riboflavin_mg`, `niacin_mg`, `pantothenic_acid_mg`, `pyridoxine_mg`, `cobalamin_mcg`, `biotin_mcg`, `folate_mcg`
- `phosphorus_mg`, `magnesium_mg`, `zinc_mg`, `selenium_mcg`, `copper_mg`, `manganese_mg`, `chromium_mcg`, `iodine_mcg`, `molybdenum_mcg`
- `saturated_fat_g`, `trans_fat_g`, `monounsaturated_fat_g`, `polyunsaturated_fat_g`, `omega3_g`, `omega6_g`
- `cholesterol_mg`
- `alcohol_g`, `caffeine_mg`, `water_g`

### `mt_meal_logs` (MealLog)
One row per meal per day: `id`, `date` (string yyyy-MM-dd), `meal_number` (1–6), `meal_name`, `meal_time`

### `mt_meal_log_items` (MealLogItem)
One row per food logged: `id`, `meal_log_id`, `ingredient_id`, `quantity_g`, `serving_desc`
+ all 74 micronutrient columns mirrored from mt_ingredients (snapshot at log time)

### `mt_recipes` (Recipe)
`id`, `name`, `serving_size_g`, `total_weight_g`, + macro totals, linked to `mt_recipe_ingredients`

---

## API Endpoints (summary)

### Foods `/api/v1/foods/`
- `GET /` — list all (optional `?source=custom`)
- `GET /search?q=...` — search across all sources
- `GET /restaurant?brand=...` — restaurant items
- `GET /usda/search?q=...` — USDA FoodData Central search
- `POST /usda/{fdc_id}/import` — import USDA food to DB
- `POST /` — create custom food
- `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`

### Meals `/api/v1/meals/`
- `POST /` — log food `{ ingredient_id, meal_number, quantity_g, serving_desc, date, meal_time }`
- `GET /today` — today's meals
- `GET /day/{dateStr}` — returns `DailySummaryRead` with `meals: [MealRead]` inside
- `PATCH /items/{itemId}` — update logged item
- `DELETE /items/{itemId}`
- `POST /{mealId}/copy` — copy a meal to another date/meal_number
- `POST /targets` — save calorie/macro targets
- `GET /targets/latest`
- `GET /micronutrients?start=yyyy-MM-dd&end=yyyy-MM-dd`

### Vision `/api/v1/vision/`
- `POST /extract` — extract nutrition from label photo
- `POST /extract-and-save` — extract + save to My Foods
- `POST /estimate-from-ingredients` — estimate from ingredient list photo
- `POST /from-url` — estimate from URL or ingredients text
- `GET /barcode/{barcode}` — Open Food Facts lookup (returns BarcodeResult, no DB write)

### Recipes `/api/v1/recipes/`
- `GET /`, `POST /`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`

---

## Auth / Multi-tenancy

**Single-user, no auth.** There is no login, sessions, or JWT. The backend uses a hardcoded default user:

```python
DEFAULT_USER_EMAIL = "jesse@macro.app"   # meals.py (and other routers)
```

`_get_or_create_user(db)` is called at the start of every write endpoint — it fetches or creates the one User row with that email. The `mt_users` table exists (with `id`, `email`, `name`, `created_at`) but is purely internal plumbing, not exposed to the frontend. No authentication middleware is present anywhere. If multi-user support is ever needed it would require adding auth headers and scoping all queries by `user_id`.

---

## Macro Targets Schema

Table: `mt_daily_targets`

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | UUID | auto | |
| `user_id` | FK → mt_users | | always the default user |
| `target_date` | Date | required | one row per date |
| `calories` | Float | 2000.0 | kcal |
| `protein_g` | Float | 150.0 | grams |
| `fat_g` | Float | 70.0 | grams |
| `carbs_g` | Float | 250.0 | grams |
| `sodium_mg` | Float | 2300.0 | mg |
| `cholesterol_mg` | Float | 300.0 | mg |
| `created_at` | DateTime | now() | |

Unique constraint on `(user_id, target_date)` — POSTing to `/meals/targets` upserts by date. `GET /meals/targets/latest` returns the most recent row (used on app load to populate the macro rings).

Frontend sets targets via the dashboard settings modal. The `DailySummaryRead` response already embeds consumed vs. target as `MacroStat` objects (`consumed`, `target`, `remaining`, `pct`).

---

## Railway Deployment

- **Config file**: `railway.toml` (Dockerfile builder, healthcheck at `/health`)
- **No `railway.json`** — project name/service ID are in the Railway dashboard, not the repo
- **Deploy command**: `bash deploy.sh "message"` — does `git add -A && git commit && git push`; Railway auto-builds on push
- **Manual deploy**: `railway up` from project root (requires Railway CLI logged in)
- **Logs**: `railway logs` or Railway dashboard → your service → Deployments

---

## Frontend State Management

**No global state library** — pure React `useState` + prop-drilling. All shared state lives in `App.jsx`:

- `currentDate` — drives date navigation; passed as `dateStr` prop to Dashboard and modals
- `dashboardKey` — increment to force-remount Dashboard after logging food
- Modal visibility flags: `showSheet`, `showAdd`, `showCamera`, `showBarcode`, `showRecipes`, `showReports`
- `savedFood` — food object returned from camera scan, passed into AddFoodModal as `preselected`

Each page/modal manages its own local state. There is no Context, Redux, or Zustand.

---

## Common Gotchas

1. **`getDay` response shape**: Returns `DailySummaryRead` — access meals as `res.data.meals`, NOT `res.data`
2. **Serving size = null**: Many personal/imported foods have no `serving_size_g`. The log modal has an inline weight-entry UI that lets users set it and optionally save back to DB.
3. **Meal time auto-fill**: Uses `useState` (not `useRef`) for `mealTimes` so the effect re-fires after the async fetch resolves. Pattern: fetch `mealTimes`, `useEffect([mealNumber, mealTimes])` auto-fills time if `!timeEdited`.
4. **Barcode source**: Foods logged via barcode without "save to library" get `source="barcode"` so they stay out of the My Foods tab but exist in DB for history.
5. **Camera cleanup**: ZXing `reset()` alone doesn't stop the camera light. Must explicitly: `video.srcObject.getTracks().forEach(t => t.stop()); video.srcObject = null`
6. **lucide-react version**: v0.303.0 — `ChefHat` doesn't exist. Use `Utensils` instead.
7. **New DB columns**: Add `ALTER TABLE mt_ingredients ADD COLUMN IF NOT EXISTS ...` in `main.py` lifespan block. Also add to `ALTER TABLE mt_meal_log_items` if it should be snapshotted.
8. **pip in backend**: Use `pip install --break-system-packages` if running locally.

---

## Environment Variables (Railway)
- `DATABASE_URL` — PostgreSQL connection string
- `OPENAI_API_KEY` — used by vision routes and suggest route
- `PORT` — set by Railway automatically

---

## Development Workflow
```bash
# Deploy everything
bash deploy.sh "description of change"

# Frontend dev (local)
cd frontend && npm run dev

# Backend dev (local)
cd backend && uvicorn app.main:app --reload --port 8000
```

Frontend dev proxy (`vite.config.js`) forwards `/api/*` to `http://localhost:8000`.
