"""使用者隔離、保留期限與刪除（Day 17）。不打模型。"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent.runner import AgentSession, make_session_service

RESUME = (
    Path(__file__).resolve().parents[2] / "data/resumes/sample-backend-1y.txt"
).read_text(encoding="utf-8")
NEEDLE = "沛原科技"


def _in_file(path: Path, text: str) -> bool:
    """ADK 存 JSON 時中文會變成 \\uXXXX，直接搜中文會以為已經刪乾淨了。"""
    raw = path.read_bytes()
    escaped = text.encode("unicode_escape")
    return text.encode() in raw or escaped in raw


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "s.db"


@pytest.fixture
def client(db, monkeypatch) -> TestClient:
    agent = AgentSession(session_service=make_session_service(f"sqlite+aiosqlite:///{db.as_posix()}"))
    monkeypatch.setattr(main, "_agent", agent)
    return TestClient(main.app)


def _start(client) -> tuple[str, str]:
    r = client.post("/agent/sessions", json={"resume_text": RESUME})
    assert r.status_code == 200
    return r.json()["session_id"], r.json()["token"]


def test_stranger_gets_the_same_404_as_a_missing_session(client):
    sid, _ = _start(client)
    stranger = {"X-Session-Token": "not-the-owner"}

    r1 = client.post(f"/agent/sessions/{sid}/messages", json={"message": "hi"}, headers=stranger)
    r2 = client.delete(f"/agent/sessions/{sid}", headers=stranger)
    r3 = client.delete("/agent/sessions/no-such-session", headers=stranger)

    assert r1.status_code == r2.status_code == r3.status_code == 404
    assert r1.json() == r2.json() == r3.json()


def test_token_is_required(client):
    sid, _ = _start(client)
    assert client.delete(f"/agent/sessions/{sid}").status_code == 422


def test_owner_can_delete_once(client):
    sid, token = _start(client)
    owner = {"X-Session-Token": token}
    assert client.delete(f"/agent/sessions/{sid}", headers=owner).status_code == 204
    assert client.delete(f"/agent/sessions/{sid}", headers=owner).status_code == 404


def test_token_is_not_stored(client, db):
    _, token = _start(client)
    assert token.encode() not in db.read_bytes()


def test_deleted_resume_is_gone_from_the_file(client, db):
    """刪掉的 row 不能只是被標成可重用，內容也要從檔案裡消失。"""
    sid, token = _start(client)
    assert _in_file(db, NEEDLE)

    client.delete(f"/agent/sessions/{sid}", headers={"X-Session-Token": token})
    assert not _in_file(db, NEEDLE)


def test_purge_only_removes_expired_sessions(db):
    agent = AgentSession(session_service=make_session_service(f"sqlite+aiosqlite:///{db.as_posix()}"))

    async def run():
        s = await agent.start("u1", RESUME)
        kept = await agent.purge_expired(ttl_hours=24)
        removed = await agent.purge_expired(ttl_hours=0)
        return s.id, kept, removed, await agent.exists("u1", s.id)

    _, kept, removed, still_there = asyncio.run(run())
    assert (kept, removed, still_there) == (0, 1, False)
    assert not _in_file(db, NEEDLE)
