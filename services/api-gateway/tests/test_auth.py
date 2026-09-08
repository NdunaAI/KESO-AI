"""Tests for the self-issued JWT auth flow (docs/07-security-auth.md #7.1-7.6).

Runs against an in-memory SQLite database instead of Postgres -- the ORM
models in app/db_models.py are deliberately cross-dialect (Uuid, JSON) so
this works without a running Postgres instance.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.db_models import User, UserScope
from app.main import app
from app.security import hash_password

TEST_PASSWORD = "correct horse battery staple"

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="module", autouse=True)
def _schema_and_seed_user():
    async def _setup() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with TestSessionLocal() as db:
            user = User(
                email="pm@keso.org",
                password_hash=hash_password(TEST_PASSWORD),
                display_name="Alice PM",
                roles=["project_manager"],
            )
            db.add(user)
            await db.flush()
            db.add(UserScope(user_id=user.id, scope_type="settlement", scope_value="A"))
            await db.commit()

    asyncio.run(_setup())
    yield


client = TestClient(app)


def _login(password: str = TEST_PASSWORD) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": "pm@keso.org", "password": password})
    assert resp.status_code == 200
    return resp.json()


def test_login_rejects_unknown_user():
    resp = client.post("/api/v1/auth/login", json={"email": "nobody@keso.org", "password": "x"})
    assert resp.status_code == 401


def test_login_rejects_wrong_password():
    resp = client.post("/api/v1/auth/login", json={"email": "pm@keso.org", "password": "wrong"})
    assert resp.status_code == 401


def test_login_issues_tokens_with_scope():
    tokens = _login()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] > 0


def test_access_token_authorizes_protected_endpoint():
    tokens = _login()
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "pm@keso.org"
    assert body["display_name"] == "Alice PM"
    assert body["roles"] == ["project_manager"]
    assert body["scope"]["settlements"] == ["A"]


def test_protected_endpoint_rejects_missing_token():
    resp = client.get("/api/v1/auth/me")
    # HTTPBearer's status for a missing Authorization header has varied
    # across fastapi/starlette versions (401 vs 403); either is a correct
    # rejection for this test's purposes.
    assert resp.status_code in (401, 403)


def test_protected_endpoint_rejects_garbage_token():
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_refresh_rotates_and_revokes_old_token():
    tokens = _login()
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


def test_logout_revokes_refresh_token():
    tokens = _login()
    logout_resp = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout_resp.status_code == 204

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_resp.status_code == 401
