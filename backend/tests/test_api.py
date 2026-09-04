from datetime import date, timedelta
from io import BytesIO

import pytest

from tests.conftest import postgres_up

pytestmark = pytest.mark.skipif(not postgres_up(), reason="PostgreSQL kapalı")


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


def test_meetings_require_login(client):
    response = client.get("/api/v1/meetings")
    assert response.status_code in {401, 403}


def test_register_login_me(client):
    if not postgres_up():
        pytest.skip("PostgreSQL kapalı")
    from uuid import uuid4

    email = f"pytest-{uuid4().hex[:12]}@example.com"
    created = client.post("/api/v1/auth/register", json={"email": email, "password": "testpass1"})
    assert created.status_code == 201
    token = created.json()["access_token"]
    user_id = created.json()["user"]["user_id"]

    again = client.post("/api/v1/auth/register", json={"email": email, "password": "testpass1"})
    assert again.status_code == 409

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "yanlis12"})
    assert login.status_code == 401

    ok = client.post("/api/v1/auth/login", json={"email": email, "password": "testpass1"})
    assert ok.status_code == 200

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    from app.core.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is not None:
            db.delete(user)
            db.commit()
    finally:
        db.close()


def test_short_password_rejected(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "kisa@example.com", "password": "123"},
    )
    assert response.status_code == 422


def test_people_unique_per_account(auth_client):
    first = auth_client.post("/api/v1/people", json={"name": "Hasan", "note": "satış"})
    assert first.status_code == 201
    dup = auth_client.post("/api/v1/people", json={"name": "hasan"})
    assert dup.status_code == 409
    listed = auth_client.get("/api/v1/people")
    assert listed.status_code == 200
    names = [row["name"] for row in listed.json()["items"]]
    assert "Hasan" in names


def test_create_meeting_and_list(auth_client):
    files = {"audio": ("demo.mp3", BytesIO(b"ID3fakeaudio"), "audio/mpeg")}
    data = {
        "title": "Pytest toplantı",
        "date": "2026-09-01T10:00:00",
        "attendees": "Ali, Ayşe",
        "language": "tr",
    }
    created = auth_client.post("/api/v1/meetings", data=data, files=files)
    assert created.status_code == 201, created.text
    meeting_id = created.json()["meeting_id"]
    assert created.json()["status"] == "uploaded"
    assert created.json()["language"] == "tr"

    listed = auth_client.get("/api/v1/meetings")
    ids = [row["meeting_id"] for row in listed.json()["items"]]
    assert meeting_id in ids

    detail = auth_client.get(f"/api/v1/meetings/{meeting_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Pytest toplantı"

    missing = auth_client.get("/api/v1/meetings/99999999")
    assert missing.status_code == 404


def test_task_due_date_rules(auth_client):
    files = {"audio": ("demo.mp3", BytesIO(b"ID3fakeaudio"), "audio/mpeg")}
    meeting = auth_client.post(
        "/api/v1/meetings",
        data={"title": "Görev toplantısı", "date": "2026-09-01T10:00:00", "language": "tr"},
        files=files,
    )
    assert meeting.status_code == 201, meeting.text
    meeting_id = meeting.json()["meeting_id"]

    no_date = auth_client.post(
        "/api/v1/tasks",
        json={"meeting_id": meeting_id, "title": "Ara", "description": "x"},
    )
    assert no_date.status_code == 422

    past = auth_client.post(
        "/api/v1/tasks",
        json={
            "meeting_id": meeting_id,
            "title": "Ara",
            "description": "x",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert past.status_code == 422

    due = (date.today() + timedelta(days=7)).isoformat()
    created = auth_client.post(
        "/api/v1/tasks",
        json={
            "meeting_id": meeting_id,
            "title": "Teklifi gönder",
            "description": "mail at",
            "assignee": "Hasan",
            "due_date": due,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["assignee"] == "Hasan"
    assert created.json()["status"] == "in_progress"

    board = auth_client.get("/api/v1/tasks")
    assert board.status_code == 200
    titles = [row["title"] for row in board.json()["items"]]
    assert "Teklifi gönder" in titles
