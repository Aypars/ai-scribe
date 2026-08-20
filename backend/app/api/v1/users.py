from fastapi import APIRouter

router = APIRouter()


@router.get("")
def list_users() -> dict:
    """Placeholder — Hafta 3 CRUD."""
    return {"items": [], "total": 0, "page": 1, "page_size": 20}
