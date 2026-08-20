from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
def dashboard_summary() -> dict:
    """Placeholder — Hafta 5 dashboard."""
    return {
        "meetings_count": 0,
        "ready_analyses_count": 0,
        "open_tasks_count": 0,
        "recent_meetings": [],
        "upcoming_tasks": [],
    }
