# Macro Tracker — Setup & Deployment Guide

## Project Structure

```
Macro Tracker App/
├── backend/                  ← FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── main.py           ← FastAPI entry point + lifespan
│   │   ├── config.py         ← All settings (env vars)
│   │   ├── database.py       ← Async SQLAlchemy engine
│   │   ├── models/models.py  ← 8 ORM tables
│   │   ├── schemas/          ← Pydantic v2 request/response shapes
│   │   ├── routers/          ← foods, meals, recipes, vision, suggest, api_keys
│   │   └── services/         ← usda.py, vision_ocr.py
│   ├── alembic/              ← Database migrations
│   ├── scripts/
│   │   └── seed_ingredients.py  ← Seeds your CSV + custom recipes
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/                 ← React 18 + Vite + Tailwind CSS
│   └── src/
│       ├── pages/Dashboard.jsx
│       ├── components/       ← MacroSummaryCards, MealSection, AddFoodModal,
│       │                        VisionModal, SuggestModal
│       └── api/client.js     ← Typed API layer
├── railway.toml              ← One-click Railway deploy config
└── SETUP.md                  ← This file
```

---

## Step 1 — Local Development

### Backend

```bash
cd "Macro Tracker App/backend"

# 1. Create virtual env
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env file and fill in your values
cp .env.example .env
# Edit .env:
#   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/macro_tracker
#   USDA_API_KEY=<your key from https://fdc.nal.usda.gov/api-key-signup.html>
#   OPENAI_API_KEY=sk-...

# 4. Start Postgres (Docker quickstart)
docker run -d --name pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16

# 5. Run the API (tables auto-created on first start)
uvicorn app.main:app --reload

# 6. Seed your restaurant + custom ingredient database
python -m scripts.seed_ingredients
```

API docs available at: http://localhost:8000/docs

### Frontend

```bash
cd "Macro Tracker App/frontend"
npm install
npm run dev
# → http://localhost:5173
```

---

## Step 2 — Railway Deployment

1. Push the entire `Macro Tracker App/` folder to a GitHub repo.
2. Go to railway.app → New Project → Deploy from GitHub repo.
3. Railway auto-detects the `railway.toml` and builds the Dockerfile.
4. Add a PostgreSQL plugin in Railway — it auto-injects `DATABASE_URL`.
5. Set environment variables in Railway dashboard:
   - `USDA_API_KEY`
   - `OPENAI_API_KEY`
   - `CORS_ORIGINS` = your frontend domain
   - `SECRET_KEY` = a long random string
   - `APP_ENV` = production

6. After first deploy, run the seeder:
   ```bash
   railway run python -m scripts.seed_ingredients
   ```

---

## Step 3 — API Key for External Tools (Mac Dashboard / Sheets)

```bash
# Create a key
curl -X POST http://localhost:8000/api/v1/api-keys/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Mac Dashboard"}'

# Returns: { "raw_key": "mt_xxxx..." }  ← save this

# Use in external tool
curl http://localhost:8000/api/v1/meals/today \
  -H "Authorization: Bearer mt_xxxx..."
```

---

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/meals/today` | Full daily summary (targets, consumed, meals) |
| POST | `/api/v1/meals/` | Log food to a meal (auto-increments meal number) |
| GET | `/api/v1/meals/day/2026-04-16` | Historical diary |
| POST | `/api/v1/meals/targets` | Set macro targets |
| GET | `/api/v1/foods/search?q=chicken` | Search local DB |
| GET | `/api/v1/foods/restaurant?brand=Chipotle` | Browse restaurant items |
| GET | `/api/v1/foods/usda/search?q=turkey` | Search USDA FoodData Central |
| POST | `/api/v1/foods/usda/{fdc_id}/import` | Import USDA item to local DB |
| POST | `/api/v1/recipes/` | Create recipe blend (Turkey & Rice, etc.) |
| POST | `/api/v1/vision/extract` | Upload photo → extract macros (GPT-4o-mini) |
| GET | `/api/v1/suggest/?log_date=2026-04-16` | "What should I eat?" top 3 |

---

## Database Schema (8 tables)

```
users              → single profile row
daily_targets      → per-day macro goals (calories / P / F / C / Na / Chol)
ingredients        → unified food DB (source: usda | restaurant | custom)
recipes            → custom blends with computed macro totals
recipe_ingredients → junction: ingredient × qty_g per recipe
meal_logs          → Meal 1, Meal 2, … per day (denormalised totals)
meal_log_items     → individual food entries, macros snapshotted at log time
api_keys           → SHA-256 hashed tokens for external tool access
```

---

## Next Steps (Phase 2)

- [ ] Alembic migration: `alembic revision --autogenerate -m "initial"`
- [ ] Add barcode lookup (Open Food Facts API)
- [ ] Weight-based water / hydration tracking
- [ ] Recharts weekly macro trend chart in Dashboard
- [ ] Recipe editor UI in frontend
- [ ] PWA manifest + service worker for offline
- [ ] Push to GitHub → auto-deploy on Railway
