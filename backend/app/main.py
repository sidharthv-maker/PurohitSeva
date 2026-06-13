from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, bookings, pandits, reviews, services, webhooks

app = FastAPI(
    title="PurohitSeva API",
    version="1.0.0",
    description="Backend for the PurohitSeva purohit-booking platform.",
)

# CORS — frontend is hosted separately (Vercel), so it calls this API cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to your Vercel URL later
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
# Webhooks sit outside /api/v1 — Razorpay dashboard points here directly
app.include_router(webhooks.router)


@app.get("/")
def root():
    return {"message": "PurohitSeva API — see /docs"}