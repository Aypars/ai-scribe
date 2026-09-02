from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()


@router.get("")
def list_users(_user: User = Depends(get_current_user)) -> dict:
    """Placeholder — kullanıcı listesi henüz yok."""
    return {"items": [], "total": 0, "page": 1, "page_size": 20}
