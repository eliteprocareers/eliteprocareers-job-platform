"""
FastAPI app entrypoint -- Phase 3 (Public Web Platform) API layer.

Run locally:
    uvicorn eliteprocareers.api.main:app --reload

This is a thin HTTP layer over the existing service/repository modules
(profiles/, jobs/, matching/) -- it deliberately contains no business
logic of its own.

Auth model: every non-public endpoint requires `Authorization: Bearer
<supabase_access_token>` (see api/dependencies.py). There is no
service_role usage anywhere in this API -- that key stays reserved for
backend jobs (ingestion, matching runs), per matching_service.py's
existing docstring warning.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from eliteprocareers.api.routers import applications, auth, documents, matches, profile, tracks
from eliteprocareers.api.schemas import HealthResponse
from eliteprocareers.db.client import SupabaseError
from eliteprocareers.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ElitePro AI Platform API",
    description="Job discovery, scoring, and application automation.",
    version="0.1.0",
)

# CORS is wide open for local/dev bring-up. Before this is deployed anywhere
# public (Phase 3's remaining Deployment item), replace allow_origins with
# the actual frontend origin(s) -- this is a placeholder, not a decision.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://eliteprocareers-frontend.vercel.app",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(tracks.router)
app.include_router(matches.router)
app.include_router(documents.router)
app.include_router(applications.router)


@app.exception_handler(SupabaseError)
def handle_supabase_error(request: Request, exc: SupabaseError) -> JSONResponse:
    """Any unhandled PostgREST failure surfaces as a generic 502 rather
    than leaking raw PostgREST error text/schema details to the client.
    Full detail still goes to the server log.
    """
    logger.error("Supabase error handling %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=502,
        content={"detail": "Upstream data error. Please try again."},
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/", tags=["health"])
def root() -> dict:
    """Landing response so the bare domain doesn't 404 -- points callers
    at the interactive docs and health check rather than serving nothing.
    """
    return {
        "name": "ElitePro AI Platform API",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }
