"""
Macro Tracker — FastAPI entry point.

In production (Railway) the built React app lives in ./static.
FastAPI serves the API on /api/v1/* and falls back to index.html
for all other routes so React Router works correctly.
"""
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from app.config import get_settings
from app.database import Base, engine
from app.routers import foods, meals, recipes, vision, suggest, api_keys

settings = get_settings()

STATIC_DIR = Path(__file__).parent.parent / "static"


# ── Lifespan: create tables on startup ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = settings.DATABASE_URL
    masked = db_url[:30] + "..." if len(db_url) > 30 else db_url
    print(f"🚀 Starting Macro Tracker — DB: {masked}", flush=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Idempotent column additions — safe to run on every deploy.
            # create_all only creates missing tables; ALTER TABLE adds missing columns.
            new_cols = [
                "ALTER TABLE mt_ingredients ADD COLUMN IF NOT EXISTS added_sugar_g  FLOAT",
                "ALTER TABLE mt_ingredients ADD COLUMN IF NOT EXISTS potassium_mg   FLOAT",
                "ALTER TABLE mt_ingredients ADD COLUMN IF NOT EXISTS vitamin_d_mcg  FLOAT",
                "ALTER TABLE mt_ingredients ADD COLUMN IF NOT EXISTS calcium_mg     FLOAT",
                "ALTER TABLE mt_ingredients ADD COLUMN IF NOT EXISTS iron_mg        FLOAT",
            ]
            for stmt in new_cols:
                await conn.execute(text(stmt))
        print("✅ Database tables ready", flush=True)
    except Exception as e:
        print(f"❌ Database connection failed: {e}", flush=True)
        print("⚠️  App will start but DB calls will fail — check DATABASE_URL", flush=True)
    yield
    await engine.dispose()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Macro Tracker API",
    description="High-performance personal nutrition analytics engine.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # safe — API is personal use only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers ───────────────────────────────────────────────────────────────
app.include_router(foods.router,    prefix="/api/v1")
app.include_router(meals.router,    prefix="/api/v1")
app.include_router(recipes.router,  prefix="/api/v1")
app.include_router(vision.router,   prefix="/api/v1")
app.include_router(suggest.router,  prefix="/api/v1")
app.include_router(api_keys.router, prefix="/api/v1")


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Meta"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Serve React frontend (production build) ───────────────────────────────────
# Mount static assets (JS, CSS, images) from the Vite build output
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # Catch-all: return index.html for any non-API route so React Router works
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = STATIC_DIR / "index.html"
        return FileResponse(index)


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ Unhandled error on {request.url}: {exc}", flush=True)
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {str(exc)[:200]}"},
    )
