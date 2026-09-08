# Macro Tracker — Claude Code Context

## Project Overview
A mobile-first macro/nutrition tracking web app. Built as a single Railway deployment: FastAPI serves both the REST API and the production React build from `./static`.

- **Live URL**: https://macro-tracker-production-207a.up.railway.app (Railway service `Macro-Tracker`, project `jubilant-mindfulness`)
- **Stack**: React 18 + Vite + Tailwind CSS (frontend) · FastAPI + SQLAlchemy async + PostgreSQL (backend)
- **Deploy**: `bash deploy.sh "commit message"` — commits everything, pushes to GitHub, Railway auto-builds

---

## Repo Structure

```
Macro Tracker App/
├── deploy.sh                  # Deploy: pre-flight checks, commit, push
├── rotate_db_password.sh      # Rotate the Railway Postgres password (--dry-run)
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
        ├── config.py          # Settings (DATABASE_URL, ANTHROPIC_API_KEY, etc.)
        ├── database.py        # Async SQLAlchemy engine + session
        ├── auth.py            # PBKDF2 hashing, token issue/verify, require_auth
        ├── models/models.py   # ORM models: Ingredient, MealLog, MealLogItem, Recipe, etc.
        ├── schemas/schemas.py # Pydantic schemas
        └── routers/
            ├── foods.py       # CRUD + USDA search/import + restaurant lookup
            ├── meals.py       # Log food, get day/today, update/delete items, copy meal, targets, micronutrients
            ├── recipes.py     # CRUD recipes
            ├── vision.py      # AI label scan, barcode lookup (Open Food Facts), URL/text nutrition
            ├── suggest.py     # AI meal suggestions
            ├── auth.py        # /auth/status, /login, /password  (NOT gated)
            ├── export.py      # CSV + ZIP export of everything
            └── api_keys.py    # API key management (legacy, unused by the app)
```

---

## Key Architecture Patterns

### Frontend
- **Single-page app** — two main tabs ("Today" / "Library") in `App.jsx`, plus modals
- **Bottom nav**: Today | Library | [+] | Estimate | Suggest
- **[+] action sheet**: Search Foods, Scan Barcode, Scan Label (camera),
  Estimate a Meal, From Recipes
- **Hamburger (top right)**: Reports, Settings (macro targets), My Account
  (password), Export data
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
  - `"usda"` — imported from USDA FoodData Central (26 rows)
  - `"cnf"` — Canadian Nutrient File, bulk-imported (~5,980 rows)
  - `"cofid"` — UK CoFID, bulk-imported (~2,845 rows)
  - `"estimated_component"` — a component of an AI photo-estimated meal
- **Serving size scaling** — the core invariant of this codebase:
  ```
  base_g = serving_size_g or 100.0     # NULL serving_size_g means "stored per 100 g"
  ratio  = logged_quantity_g / base_g
  ```
  A NULL `serving_size_g` means the macros are per 100 g — it does **not** mean
  "scale by the logged quantity". Getting this wrong makes macros refuse to
  change when you edit the weight. The rule is duplicated in
  `meals.py` (`_scale_macros`, `_accumulate_ingredient_micros`), `recipes.py`
  (`_compute_recipe_totals`), `export.py`, `vision.py`, and in the frontend's
  `calcTotals()` / `LogFoodModal`. **Change all of them together.**
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
- `GET /micronutrients?start=yyyy-MM-dd&end=yyyy-MM-dd` (range capped at 732 days)
- `GET /daily-series`, `GET /nutrient-series`, `GET /nutrient-sources` — Reports charts
- `PATCH|DELETE /items/{id}/components/{component_id}` — edit one component of an
  AI-estimated meal

### Vision `/api/v1/vision/`
- `POST /extract` — extract nutrition from label photo
- `POST /extract-and-save` — extract + save to My Foods
- `POST /estimate-meal` — photo of a *meal* → AI estimate, broken into components
- `POST /refine-meal-estimate` — re-estimate after the user corrects components
- `POST /estimate-from-ingredients` — estimate from ingredient list photo
- `POST /from-url` — estimate from URL or ingredients text
- `GET /barcode/{barcode}` — Open Food Facts lookup (returns BarcodeResult, no DB write)

### Recipes `/api/v1/recipes/`
- `GET /`, `POST /`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`

### Auth `/api/v1/auth/` — **not gated**
- `GET /status` — `{ auth_required, authenticated, password_is_set }`
- `POST /login` — password only, no username. Returns a bearer token.
- `POST /password` — set/change the password; returns a fresh token

### Export `/api/v1/export/`
- `GET /{kind}.csv` — one of `food_log`, `daily_totals`, `foods`, `recipes`,
  `recipe_ingredients`, `targets`
- `GET /all.zip` — all six at once

  Exports include all 85 micronutrients. Sodium and cholesterol come from the
  frozen snapshot on `mt_meal_log_items`; every other micro is **recomputed** by
  scaling `mt_ingredients` (see the serving-size invariant).

---

## Auth / Multi-tenancy

**Single user, password-gated.** `mt_users` still holds exactly one row
(`jesse@macro.app`, `DEFAULT_USER_EMAIL`) and every router calls
`_get_or_create_user(db)`; there is no per-user scoping. What changed is that
the API is now gated.

- `backend/app/auth.py` — PBKDF2-HMAC-SHA256 (16-byte salt, 600,000 iterations).
  The bearer token is `HMAC(SECRET_KEY, password_hash)`, has **no expiry**, and
  the frontend keeps it in `localStorage` (so you stay signed in).
- The password lives in `mt_users.password_hash`. `settings.APP_PASSWORD` is a
  **fallback only**, used when no hash is set yet.
- `main.py` gates every router with `dependencies=[Depends(require_auth)]`.
  `/auth` is deliberately open — it is how you get a token.
- **`require_auth` is a no-op when no password is configured at all.** If both
  the DB hash and `APP_PASSWORD` are empty the API is wide open, and
  `GET /auth/status` reports `auth_required: false`. Check that endpoint before
  assuming the app is protected.
- Users change their password in-app via the hamburger → My Account
  (`AccountModal.jsx`), which POSTs to `/auth/password` and returns a fresh token.

Multi-user support would still require scoping every query by `user_id`.

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

Frontend sets targets via `SettingsModal` (hamburger → Settings) as
**percentages of total calories** — protein/carbs/fat must sum to 100 — which
are converted to grams (`kcal * pct/100`, at 4/4/9 kcal per gram) before the
POST. The table itself only ever stores grams. The `DailySummaryRead` response already embeds consumed vs. target as `MacroStat` objects (`consumed`, `target`, `remaining`, `pct`).

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
9. **USDA nutrients are PER 100 g.** `servingSize` in the API response is label
   metadata, *not* the basis of the numbers. Storing it in `serving_size_g`
   inflates everything by `100/serving` (a 39 g cake at 410 kcal/100g displayed
   as 1051). USDA foods must always be stored with `serving_size_g = 100`.
10. **Claude Sonnet returns `[thinking, text]` content blocks.** Never read
    `content[0]["text"]` — find the block whose `type == "text"`. `vision.py`
    has a `_response_text(data)` helper; use it for every call.
11. **CSS variables are RGB channels, not colors** (`--surface-1: 255 255 255`)
    so Tailwind alpha modifiers work. In inline styles you must write
    `rgb(var(--surface-1))` — a bare `var(--surface-1)` renders transparent.
12. **Dark mode** toggles by clicking the "M" logo; it swaps the `:root`
    variables in `index.css`.
13. **Macro targets are entered as % of total calories** in `SettingsModal`
    (must sum to 100) but are **stored as grams** in `mt_daily_targets`.
14. **Recipes have proxy ingredients** — `mt_ingredients` rows with `recipe_id`
    set. They appear in food search alongside the real food, which is why the
    library shows apparent duplicates. Deleting a recipe orphans its proxy
    (`recipe_id` → NULL).
15. **`deploy.sh` runs pre-flight checks** (backend imports, frontend build) and
    refuses to push if either fails. A green "✓ Deployed" means the *push*
    succeeded — check Railway for the build result.

---

## Environment Variables (Railway)
- `DATABASE_URL` — PostgreSQL connection string
- `ANTHROPIC_API_KEY` — all AI features (vision, meal estimation, suggestions)
- `ANTHROPIC_VISION_MODEL` — defaults to `claude-sonnet-5`. **Every** AI feature
  in this app uses Sonnet.
- `SECRET_KEY` — signs the auth token. Changing it invalidates every issued
  token (everyone is signed out); it does **not** change the password.
- `APP_PASSWORD` — fallback password, only consulted when `mt_users.password_hash`
  is empty. Leaving both unset disables auth entirely.
- `USDA_API_KEY` — FoodData Central (`DEMO_KEY` is heavily rate-limited)
- `PORT` — set by Railway automatically

The app talks to Postgres over `postgres.railway.internal` (the private network).
`mainline.proxy.rlwy.net` is the public proxy and should only be used from your
Mac (e.g. backups) — not by a deployed service.

---

## Backups & Operations

Backups live **outside the repo** at `~/MacroTrackerBackups/` (they were in
`~/Documents` originally, but macOS TCC blocks launchd from reading that, so the
LaunchAgent silently failed with "Operation not permitted").

- `backup.sh` — `pg_dump` custom format + plain SQL, keeps the last 30, and
  aborts if the dump comes out under 1 MB
- `.dbenv` — connection credentials, `chmod 600`, sourced by the script
- LaunchAgent `com.jesse.macrotracker.backup` runs it daily at 12:30
- Backups connect over the **public** proxy (they run from the Mac, not Railway)

`rotate_db_password.sh` rotates the Postgres password. Note that setting
`POSTGRES_PASSWORD` alone does nothing — that variable is only read by the
Postgres image at initdb, so the script issues `ALTER ROLE`, then re-syncs the
four `Postgres` service variables, `Macro-Tracker`, `workout-tracker`, and
`.dbenv`. It supports `--dry-run`.

**The Postgres instance is shared** with the workout-tracker app (same Railway
project, `jubilant-mindfulness`). Anything that touches roles, credentials, or
connection limits affects both.

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
