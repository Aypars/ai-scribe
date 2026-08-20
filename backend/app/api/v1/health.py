from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import check_connection

router = APIRouter()


@router.get("/health")
def api_health() -> dict[str, str]:
    try:
        check_connection()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "connected"}
