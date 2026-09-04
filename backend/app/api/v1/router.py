from fastapi import APIRouter

from app.api.v1 import auth, health, meetings, people, tasks

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(people.router, prefix="/people", tags=["people"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
