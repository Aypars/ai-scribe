from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal, check_connection
from app.main import app
from app.models.user import User


def postgres_up() -> bool:
    try:
        check_connection()
        return True
    except SQLAlchemyError:
        return False


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.cancel_all_transcriptions", lambda: None)
    monkeypatch.setattr("app.api.v1.meetings.schedule_transcription", lambda *_a, **_k: None)
    monkeypatch.setattr("app.api.v1.meetings.schedule_analysis", lambda *_a, **_k: None)
    monkeypatch.setattr("app.api.v1.meetings.schedule_speaker_match", lambda *_a, **_k: None)
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client):
    if not postgres_up():
        pytest.skip("PostgreSQL kapalı")
    email = f"pytest-{uuid4().hex[:12]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass1"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    user_id = payload["user"]["user_id"]
    client.headers["Authorization"] = f"Bearer {payload['access_token']}"
    yield client
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is not None:
            db.delete(user)
            db.commit()
    finally:
        db.close()
