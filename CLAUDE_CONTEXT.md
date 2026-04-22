# Macro Tracker App — Claude Context Prompt

Use this as the opening message in a new thread to continue development.

---

## Project

A personal iOS-optimised macro tracking web app (React + FastAPI). Deployed on Railway. The user accesses it as a PWA on iPhone. The git remote is `origin/main` — Railway auto-deploys on push. **The user cannot push from the sandbox; they must run `git push origin main` themselves from their terminal.**

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS (custom iOS light theme) |
| Backend | FastAPI, SQLAlchemy async, PostgreSQL (Railway) |
| Fonts | System `-apple-system` stack + JetBrains Mono |
| Icons | lucide-react 0.383.0 |
| HTTP client | Axios (`/api/v1` prefix) |
| Vision OCR | Anthropic Claude API (nutrition label scanning) |
| Food database | USDA FoodData Central API + CSV-seeded restaurant brands |

---

## File Structure

```
Macro Tracker App/
├── frontend/src/
│   ├── App.jsx                          # Root layout, nav, tab routing
│   ├── index.css                        # Global CSS + Tailwind custom components
│   ├── api/client.js                    # All Axios API calls
│   ├── pages/
│   │   ├── Dashboard.jsx                # Today tab: macro summary + meal list
│   │   ├── LibraryPage.jsx              # Library tab: 3 sub-tabs (Recipes/My Foods/Restaurants)
│   │   └── RecipesPage.jsx              # (legacy, superseded by LibraryPage — can be deleted)
│   └── components/
│       ├── AddFoodModal.jsx             # Global food search + log modal (exports ModalShell)
│       ├── MealSection.jsx              # Collapsible meal card on Dashboard
│       ├── CopyMealModal.jsx            # Copy a meal to another date/meal number
│       ├── RecipeBuilderModal.jsx       # 3-step recipe create/edit modal
│       ├── VisionModal.jsx              # Camera scan → nutrition OCR → save/log
│       ├── CustomMealModal.jsx          # Bulk add multiple foods to a meal
│       ├── SuggestModal.jsx             # "What should I eat?" suggestion engine
│       ├── MacroSummaryCards.jsx        # Calorie/macro ring cards on Dashboard
│       ├── IngredientEditModal.jsx      # Edit a custom food's name/macros
│       └── LogFoodModal.jsx             # Log a library food to a meal (date + meal# + qty + time)
├── backend/app/
│   ├── main.py                          # FastAPI app, lifespan (create_all + ALTER TABLE migrations)
│   ├── database.py                      # Async SQLAlchemy engine + session
│   ├── config.py                        # Settings from env vars
│   ├── models/models.py                 # SQLAlchemy ORM models
│   ├── schemas/schemas.py               # Pydantic v2 request/response schemas
│   ├── routers/
│   │   ├── foods.py                     # /foods — ingredient CRUD, USDA search, restaurant list
│   │   ├── meals.py                     # /meals — log food, get day, edit items, copy meal
│   │   ├── recipes.py                   # /recipes — CRUD + search
│   │   ├── vision.py                    # /vision — OCR extract + save
│   │   ├── suggest.py                   # /suggest — macro-budget recommendation engine
│   │   └── api_keys.py                  # /api-keys — key management
│   └── services/
│       ├── vision_ocr.py                # Claude API call for nutrition label OCR
│       └── usda.py                      # USDA FoodData Central API proxy
```

---

## Design System (Tailwind custom tokens)

```js
colors: {
  surface: { DEFAULT: "#F2F2F7", 1: "#FFFFFF", 2: "#F2F2F7", 3: "#E5E5EA" },
  border: "#C6C6C8",
  foreground: "#111827",
  accent: { blue: "#007AFF", green: "#34C759", orange: "#FF9500", red: "#FF3B30", purple: "#AF52DE" },
  muted: "#8E8E93",
  subtle: "#6C6C70",
}
```

**Custom CSS classes** (in `index.css`):
- `.card`, `.card-sm`, `.card-no-pad` — white rounded cards with shadow
- `.btn-primary`, `.btn-ghost`, `.btn-outline`, `.btn-danger` — button styles
- `.input` — `bg-surface-2 border rounded-xl px-3 py-2.5 text-sm w-full focus:border-accent-blue`
- `.list-row`, `.section-label`, `.macro-bar`

---

## API Endpoints

```
GET    /api/v1/foods/                    # List all ingredients (?source=custom|restaurant)
GET    /api/v1/foods/search              # Full-text search (?q=&source=&brand=&limit=)
GET    /api/v1/foods/restaurant          # Restaurant items (?brand=Chipotle)
GET    /api/v1/foods/usda/search         # USDA FoodData Central proxy
POST   /api/v1/foods/usda/{fdc_id}/import
POST   /api/v1/foods/                    # Create custom ingredient
GET    /api/v1/foods/{id}
PATCH  /api/v1/foods/{id}               # Edit ingredient
DELETE /api/v1/foods/{id}

GET    /api/v1/meals/today
GET    /api/v1/meals/day/{dateStr}       # yyyy-MM-dd
POST   /api/v1/meals/                    # Log food (ingredient_id or recipe_id + quantity_g)
PATCH  /api/v1/meals/items/{itemId}      # Edit quantity
DELETE /api/v1/meals/items/{itemId}
POST   /api/v1/meals/{mealId}/copy       # Copy meal to another date/meal number
POST   /api/v1/meals/targets             # Set daily macro targets
GET    /api/v1/meals/targets/latest

GET    /api/v1/recipes/                  # List all (?q= for search)
POST   /api/v1/recipes/
GET    /api/v1/recipes/{id}
PATCH  /api/v1/recipes/{id}
DELETE /api/v1/recipes/{id}

POST   /api/v1/vision/extract            # OCR only (multipart/form-data, 1-2 images)
POST   /api/v1/vision/extract-and-save   # OCR + save as custom ingredient

GET    /api/v1/suggest/                  # Macro-budget food suggestions
```

---

## Key Architecture Decisions

### Modal system
All modals use `ModalShell` exported from `AddFoodModal.jsx`:
```jsx
// Sheet pinned to bottom, clips to exact screen width
<div className="fixed inset-0 z-50">
  <div className="absolute inset-0 bg-black/40" onClick={onClose} />
  <div className="absolute bottom-0 inset-x-0 overflow-hidden rounded-t-3xl shadow-2xl">
    <div className="bg-white w-full min-w-0 flex flex-col gap-4 overflow-y-auto px-4 pt-5"
         style={{ maxHeight: "85dvh", paddingBottom: "calc(90px + env(safe-area-inset-bottom, 0px))" }}>
      {/* handle pill, title bar, children */}
    </div>
  </div>
</div>
```
**iOS WebKit rule**: never put `overflow-x: hidden` and `overflow-y: auto` on the same element — WebKit converts hidden→auto. Use a non-scrolling parent with `overflow-hidden` + an inner div with only `overflow-y-auto`.

### Flexbox overflow prevention
Every flex row containing text **must** have:
- `w-full` on the row container
- `flex-1 min-w-0` on the text wrapper div
- `truncate` on the text `<p>` element
- `shrink-0` on fixed-width siblings (icons, buttons)

Without `min-w-0`, flex children refuse to shrink below their content size, pushing the layout wider than the screen.

### Root layout
```jsx
// App.jsx root div
<div className="min-h-screen bg-surface w-full max-w-md mx-auto">
```
`max-w-md` = 448px — wider than any iPhone viewport so it never clips, but caps on tablet/desktop.

### Global overflow lock
```css
/* index.css */
html, body { overflow-x: hidden; width: 100%; }
```

### DB migrations
`CREATE TABLE IF NOT EXISTS` (SQLAlchemy `create_all`) only creates missing tables. New columns use idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in the FastAPI lifespan startup handler in `main.py`.

### Dashboard refresh
`dashboardKey` state in App.jsx is incremented when food is logged, forcing Dashboard to remount and re-fetch. Pattern: `<Dashboard key={dashboardKey} ... />`.

---

## Data Model Summary

**Ingredient** (table: `mt_ingredients`): id, name, brand, source (`custom`|`personal`|`restaurant`|`usda`), calories, protein_g, fat_g, carbs_g, fiber_g, sugar_g, added_sugar_g, sodium_mg, cholesterol_mg, sat_fat_g, trans_fat_g, serving_size_g, serving_size_desc, potassium_mg, vitamin_d_mcg, calcium_mg, iron_mg, usda_fdc_id, created_at

**MealLog** (table: `mt_meal_logs`): id, log_date, meal_number (1-6), logged_at, total_calories/protein/fat/carbs/sodium/cholesterol

**MealLogItem** (table: `mt_meal_log_items`): id, meal_log_id, ingredient_id (nullable), recipe_id (nullable), quantity_g, display_name (computed), calories/protein_g/fat_g/carbs_g/sodium_mg/cholesterol_mg (computed at log time), logged_at

**Recipe** (table: `mt_recipes`): id, name, description, serving_size_g, total_weight_g, calories/protein_g/fat_g/carbs_g/sodium_mg/cholesterol_mg (computed), created_at

**RecipeIngredient**: id, recipe_id, ingredient_id, quantity_g

**DailyTarget**: id, target_date, calories/protein_g/fat_g/carbs_g/sodium_mg/cholesterol_mg

---

## Current App Features

1. **Today tab** — macro summary cards (ring progress), scrollable meal list, date navigation (prev/next day)
2. **Library tab** — segmented control with 3 sub-tabs:
   - **Recipes**: list, search, create/edit (3-step builder), delete
   - **My Foods**: custom/personal ingredients, search, edit macros, delete, log to meal (+)
   - **Restaurants**: items grouped by brand (Chipotle, Cactus Club, etc.), collapsible, log to meal (+), delete
3. **Add Food** (global + button) — search local DB + USDA + recipes simultaneously, select food, pick meal 1-6, quantity, time, log
4. **Scan** — photo OCR via Claude Vision: capture 1-2 images of nutrition label, review all extracted nutrients, save as custom ingredient and/or log to meal
5. **Copy Meal** — duplicate any meal to any date, meal number, and time
6. **Edit meal items** — change quantity inline on meal cards
7. **Delete meal items** — swipe/tap trash on meal cards
8. **Suggest** — "what should I eat?" based on remaining macro budget

---

## Macro Colour Coding (used consistently everywhere)

- Calories: `#FF9500` (orange)
- Protein: `#34C759` (green)
- Carbs: `#007AFF` (blue)
- Fat: `#FF3B30` (red)

---

## Known Issues / Pending

- `RecipesPage.jsx` is legacy (superseded by LibraryPage) — safe to delete
- The "Suggest" nav item currently just switches to Today tab instead of opening SuggestModal — could be wired up
- Vision OCR `confidence` field is parsed but not displayed to the user
- No authentication — single-user app

---

## How to Continue

Start your reply by reading any specific file you need with the Read tool before making changes. When you make changes, commit with a descriptive message and remind the user to run `git push origin main`.
