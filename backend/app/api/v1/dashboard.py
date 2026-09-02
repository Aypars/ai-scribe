from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()


@router.get("/summary")
def dashboard_summary(_user: User = Depends(get_current_user)) -> dict:
    """Placeholder — frontend dashboard kendi listelerini kullanır."""
    return {
        "meetings_count": 0,
        "ready_analyses_count": 0,
        "open_tasks_count": 0,
        "recent_meetings": [],
        "upcoming_tasks": [],
    }
