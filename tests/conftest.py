import pytest
from fastapi.testclient import TestClient
from app import db
from app.main import app, preview_sessions

@pytest.fixture()
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'demo.sqlite3')
    db.init_db()
    preview_sessions.clear()
    with TestClient(app) as c:
        yield c
