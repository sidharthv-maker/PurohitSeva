from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import auth, bookings, pandits, reviews, services, webhooks

app = FastAPI(
    title="PurohitSeva API",
    version="1.0.0",
    description="Backend for the PurohitSeva purohit-booking platform.",
)

# CORS — allow the frontend (served separately or as file://) to call the API.
# Restrict origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes — all under /api/v1
API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(pandits.router, prefix=API_PREFIX)
app.include_router(services.router, prefix=API_PREFIX)
app.include_router(bookings.router, prefix=API_PREFIX)
app.include_router(reviews.router, prefix=API_PREFIX)
# Webhooks sit outside the /api/v1 prefix — Razorpay dashboard points here directly
app.include_router(webhooks.router)

# ---------------------------------------------------------------------------
# Serve the frontend from the same process (optional — convenient for demos).
# Run `uvicorn app.main:app --reload` from the backend/ directory.
# The frontend lives one level up in ../frontend/.
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@app.get("/", include_in_schema=False)
def serve_index():
    if (FRONTEND_DIR / "page.html").exists():
        return FileResponse(FRONTEND_DIR / "page.html")
    return {"message": "PurohitSeva API — see /docs"}


if FRONTEND_DIR.exists():
    # Mount frontend static assets (CSS, JS, images) at root.
    # Explicit routes above take precedence over this mount.
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
