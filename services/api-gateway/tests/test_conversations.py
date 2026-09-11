"""Tests for conversation persistence and the /conversations, /feedback
endpoints (docs/04-data-model.md #4.1).

Exercises app/routers/chat.py's persistence helpers directly (same
functions the streaming /chat endpoint calls) rather than mocking the
orchestrator's SSE stream -- that covers the actual new logic (ownership
scoping, soft-delete, citation nesting) without fragile HTTP-level mocking.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db_models import User as UserRow
from app.main import app
from app.routers.chat import _get_or_create_conversation, _save_assistant_message, _save_user_message
from app.security import hash_password
from tests.conftest import TestSessionLocal, ensure_schema

PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="module", autouse=True)
def _seed_users():
    async def _setup() -> None:
        await ensure_schema()
        async with TestSessionLocal() as db:
            db.add(UserRow(email="owner@keso.org", password_hash=hash_password(PASSWORD), display_name="Owner", roles=["project_manager"]))
            db.add(UserRow(email="other@keso.org", password_hash=hash_password(PASSWORD), display_name="Other", roles=["project_manager"]))
            await db.commit()

    asyncio.run(_setup())
    yield


client = TestClient(app)


def _auth_header(email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _seed_conversation() -> uuid.UUID:
    """Creates one conversation for owner@keso.org via the same helpers
    chat.py uses, with one user turn and one cited assistant turn."""

    async def _seed() -> uuid.UUID:
        async with TestSessionLocal() as db:
            result = await db.execute(select(UserRow).where(UserRow.email == "owner@keso.org"))
            owner_id = result.scalar_one().id

        question = "What is the status of Kliptown?"
        conversation_id = await _get_or_create_conversation(owner_id, None, question)
        await _save_user_message(conversation_id, question)
        await _save_assistant_message(
            conversation_id,
            'The status of Kliptown is "Pending" [T1].',
            [
                {
                    "id": "T1",
                    "source_type": "record",
                    "source_system": "oracle",
                    "uri": "KESO.PROJECTS",
                    "title": "oracledb-mcp-server.get_project",
                    "confidence": None,
                }
            ],
            "stop",
        )
        return conversation_id

    return asyncio.run(_seed())


def test_list_conversations_empty_for_fresh_user():
    resp = client.get("/api/v1/conversations", headers=_auth_header("other@keso.org"))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_persisted_conversation_appears_in_list():
    _seed_conversation()
    resp = client.get("/api/v1/conversations", headers=_auth_header("owner@keso.org"))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    latest = items[0]
    assert latest["title"] == "What is the status of Kliptown?"
    assert latest["message_count"] == 2


def test_get_conversation_returns_messages_and_citations():
    conversation_id = _seed_conversation()
    resp = client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("owner@keso.org"))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"
    assert body["messages"][1]["citations"][0]["id"] == "T1"
    assert body["messages"][1]["citations"][0]["source_system"] == "oracle"


def test_conversation_is_not_visible_to_a_different_user():
    conversation_id = _seed_conversation()
    resp = client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("other@keso.org"))
    assert resp.status_code == 404


def test_delete_conversation_hides_it_from_owner():
    conversation_id = _seed_conversation()
    del_resp = client.delete(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("owner@keso.org"))
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("owner@keso.org"))
    assert get_resp.status_code == 404


def test_delete_conversation_owned_by_someone_else_is_a_silent_noop():
    conversation_id = _seed_conversation()
    # Not owned by "other" -- must not delete it or reveal that it exists.
    resp = client.delete(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("other@keso.org"))
    assert resp.status_code == 204

    still_there = client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("owner@keso.org"))
    assert still_there.status_code == 200


def test_feedback_on_own_message_succeeds():
    conversation_id = _seed_conversation()
    detail = client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("owner@keso.org")).json()
    assistant_message_id = detail["messages"][1]["id"]

    resp = client.post(
        "/api/v1/feedback",
        headers=_auth_header("owner@keso.org"),
        json={"message_id": assistant_message_id, "rating": "up"},
    )
    assert resp.status_code == 201
    assert resp.json()["id"]


def test_feedback_on_someone_elses_message_is_rejected():
    conversation_id = _seed_conversation()
    detail = client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth_header("owner@keso.org")).json()
    assistant_message_id = detail["messages"][1]["id"]

    resp = client.post(
        "/api/v1/feedback",
        headers=_auth_header("other@keso.org"),
        json={"message_id": assistant_message_id, "rating": "down"},
    )
    assert resp.status_code == 404
