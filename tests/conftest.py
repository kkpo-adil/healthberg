import pytest
from fastapi.testclient import TestClient
from app import db
from app.main import app,preview_sessions

@pytest.fixture()
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'healthberg_demo.sqlite3')
    preview_sessions.clear()
    with TestClient(app) as c:yield c

@pytest.fixture()
def login_as(client):
    def fn(role):
        from app.portal import SEED_USERS,DEMO_PASSWORD
        u=next(u for u in SEED_USERS if u[3]==role)
        r=client.post('/api/auth/login',json={'email':u[1],'password':DEMO_PASSWORD},headers={'X-Healthberg-Action':'demo'})
        assert r.status_code==200,r.text
        return u
    return fn

@pytest.fixture()
def post(client):
    return lambda path,data:client.post(path,json=data,headers={'X-Healthberg-Action':'demo'})
