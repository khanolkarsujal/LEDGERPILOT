"""
LedgerPilot — FastAPI backend.

Minimal application with health-check endpoint and restricted CORS.
Feature routes (upload, extract, export) will be added incrementally.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.extract import router as extract_router
from app.api.reports import router as reports_router

app = FastAPI(
    title="LedgerPilot API",
    description="Converts handwritten ledger photos into structured digital records.",
    version="0.1.0",
)

# CORS: restrict to the Vite dev server origin.
# Update this list when the frontend is deployed.
ALLOWED_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(extract_router)
app.include_router(reports_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Simple health-check endpoint to verify the backend is running."""
    return {"status": "ok"}
