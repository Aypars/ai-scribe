"""AI-SCRIBE FastAPI application entrypoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal, check_connection, engine, ensure_schema
from app.repositories import people as people_repo
import app.models  # noqa: F401

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    check_connection()
    ensure_schema()
    db = SessionLocal()
    try:
        people_repo.backfill(db)
    except Exception:
        logger.exception("People directory backfill failed")
    finally:
        db.close()
    yield
    engine.dispose()


app = FastAPI(
    title="AI-SCRIBE API",
    description="Ses analizli toplantı asistanı ve iş takip sistemi",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    try:
        check_connection()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "connected"}
