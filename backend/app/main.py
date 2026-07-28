from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import CLIENT_ORIGIN, USE_MOCK_DB
from app.utils.ids import now_iso

from app.routers import (
    auth, orgs, partners, referrals, settlements, tasks, dashboard, notifications,
    approvals, appointments, reviews, reports, plans, patients, queue, followups,
    billing, whatsapp, settings, booking_settings, public_booking, doctors, public_marketing,
    password_resets, subscription_renewals, partnerships, partner_plans,
)

app = FastAPI(title="ROSKYRO Healthcare OS API")

origins = CLIENT_ORIGIN.split(",") if CLIENT_ORIGIN else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    """Match the Node API's flat error-body convention (`{ error: "..." }`
    or a richer object like `{ error, requiredPillar, upgradeRequired }`)
    instead of FastAPI's default `{ "detail": ... }` wrapper -- the ported
    frontend expects the same shape the original Express routes returned.

    Registered on starlette.exceptions.HTTPException (the BASE class),
    not fastapi.HTTPException (a subclass of it) -- Starlette's router
    raises the base class directly for a path that matches no route at
    all (as opposed to a route handler explicitly raising fastapi's
    HTTPException), and a handler registered on the subclass does NOT
    catch base-class instances, only the reverse. Registering on the base
    class here catches both, so an unmatched route and an in-handler 404
    return the same `{"error": ...}` shape instead of the former
    silently falling back to FastAPI's default `{"detail": ...}` body.
    Caught by a live regression test (tests/test_health.py)."""
    if isinstance(exc.detail, dict):
        content = exc.detail
    else:
        content = {"error": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "Invalid request.", "details": exc.errors()})


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "roskyro-healthcare-os-api", "time": now_iso()}


@app.on_event("startup")
async def seed_mock_db_on_boot():
    """The mongomock client is in-process and in-memory -- it dies with the
    uvicorn worker, so there's no separate persistent database for a
    standalone `python -m app.seed` run to populate ahead of time. Auto-seed
    demo data on boot ONLY when running against the mock (USE_MOCK_DB=true).
    A real MongoDB deployment (USE_MOCK_DB=false) is never auto-seeded on
    startup -- that would silently wipe real data; run `python -m app.seed`
    manually against it once instead."""
    if USE_MOCK_DB:
        from app.seed import run as seed_run
        await seed_run()


@app.on_event("startup")
async def bootstrap_super_admin():
    """Runs on every boot, mock DB or real -- see app/admin_bootstrap.py.
    Keeps the ROSKYRO super-admin account's email/password in sync with
    ADMIN_EMAIL / ADMIN_PASSWORD, independent of whether (or when)
    `python -m app.seed` has ever been run. Registered after
    seed_mock_db_on_boot so it also reconciles anything that mock-seeding
    just created."""
    from app.admin_bootstrap import sync_super_admin
    await sync_super_admin()


@app.on_event("startup")
async def ensure_db_indexes():
    """Runs on every boot, mock DB or real -- see app/db_indexes.py. Without
    this, every query that filters by anything other than `_id` (org_id,
    email, referral_id, partner_id, ...) forces MongoDB to scan the entire
    collection, which gets steadily slower as real data accumulates.
    `create_index` is idempotent, so repeating this on every boot is safe
    and cheap once the indexes already exist."""
    from app.db_indexes import ensure_indexes
    await ensure_indexes()


app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(partners.router)
app.include_router(referrals.router)
app.include_router(settlements.router)
app.include_router(tasks.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(approvals.router)
app.include_router(appointments.router)
app.include_router(reviews.router)
app.include_router(reports.router)
app.include_router(plans.router)
app.include_router(partner_plans.router)
app.include_router(patients.router)
app.include_router(queue.router)
app.include_router(followups.router)
app.include_router(billing.router)
app.include_router(whatsapp.router)
app.include_router(settings.router)
app.include_router(booking_settings.router)
app.include_router(public_booking.router)
app.include_router(doctors.router)
app.include_router(public_marketing.router)
app.include_router(password_resets.router)
app.include_router(subscription_renewals.router)
app.include_router(partnerships.router)

# --- Serve the built React frontend from this same service (single Railway
# service, one URL) ---
#
# frontend/src/lib/api.js calls the API as a relative `/api/...` path by
# default (REACT_APP_API_URL is only used if explicitly set), which is
# exactly right here since frontend + backend are the same origin. The
# Dockerfile builds the React app (`npm run build`, via CRACO) and copies
# the output to <repo root>/frontend/build alongside this backend/ folder,
# so this single service can serve both -- no separate frontend host, no
# CORS setup needed for the deployed app itself (CORS middleware above is
# still configured for local-dev convenience, where CRA/CRACO's own dev
# server on :3000 is a different origin than :8000).
#
# This block is a no-op in local dev (`uvicorn app.main:app` straight from
# backend/ with no frontend/build present) -- CRACO's dev server proxies to
# this API instead, per package.json's "proxy" field.
_FRONTEND_BUILD_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "build"

if _FRONTEND_BUILD_DIR.is_dir():
    _static_dir = _FRONTEND_BUILD_DIR / "static"
    if _static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=_static_dir), name="frontend-static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """SPA fallback: serve a matching built file if one exists (favicon,
        manifest.json, etc.), otherwise index.html so React Router can
        handle the client-side route. Never intercepts /api/* -- an
        unmatched API path should still 404 as JSON via the handler above,
        not silently return the frontend's index.html to a client expecting
        JSON."""
        if full_path.startswith("api/") or full_path in ("api", "docs", "openapi.json", "redoc"):
            raise HTTPException(status_code=404, detail="Not found.")
        candidate = _FRONTEND_BUILD_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_BUILD_DIR / "index.html")

# No explicit catch-all needed when frontend/build is absent (local dev):
# FastAPI/Starlette already raises an HTTPException(404) for any unmatched
# path/method, and the handler above reshapes it to the same
# `{ "error": "..." }` body the Node app returns from its own catch-all 404
# middleware.
