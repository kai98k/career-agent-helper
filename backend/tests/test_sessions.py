"""Session 的保存行為（Day 16）。不打模型。"""

import asyncio

from google.adk.events import Event, EventActions
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from app.agent.runner import APP_NAME
from app.agent.tools import STATE_RESUME


def _db(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 's.db').as_posix()}"


def _answer_event(text: str, delta: dict) -> Event:
    return Event(
        author="user",
        invocation_id="i1",
        content=types.Content(role="user", parts=[types.Part(text=text)]),
        actions=EventActions(state_delta=delta),
    )


def test_session_survives_restart(tmp_path):
    """同一個資料庫開兩個 service，模擬服務重開。"""

    async def run():
        before = DatabaseSessionService(db_url=_db(tmp_path))
        s = await before.create_session(
            app_name=APP_NAME, user_id="u1", state={STATE_RESUME: "履歷全文"}
        )
        await before.append_event(s, _answer_event("SQL 有寫過", {"clarify_answers": {"SQL": "有寫過"}}))

        after = DatabaseSessionService(db_url=_db(tmp_path))
        return await after.get_session(app_name=APP_NAME, user_id="u1", session_id=s.id)

    got = asyncio.run(run())
    assert got.state[STATE_RESUME] == "履歷全文"
    assert got.state["clarify_answers"] == {"SQL": "有寫過"}
    assert got.events[0].content.parts[0].text == "SQL 有寫過"


def test_mutating_fetched_state_is_not_saved(tmp_path):
    """get_session 拿到的是複本，要改 state 只能走 event 的 state_delta。"""

    async def run():
        svc = DatabaseSessionService(db_url=_db(tmp_path))
        s = await svc.create_session(app_name=APP_NAME, user_id="u1")
        got = await svc.get_session(app_name=APP_NAME, user_id="u1", session_id=s.id)
        got.state["clarify_answers"] = {"SQL": "有寫過"}
        return await svc.get_session(app_name=APP_NAME, user_id="u1", session_id=s.id)

    assert "clarify_answers" not in asyncio.run(run()).state


def test_other_user_cannot_read_the_session(tmp_path):
    async def run():
        svc = DatabaseSessionService(db_url=_db(tmp_path))
        s = await svc.create_session(
            app_name=APP_NAME, user_id="u1", state={STATE_RESUME: "履歷全文"}
        )
        return await svc.get_session(app_name=APP_NAME, user_id="u2", session_id=s.id)

    assert asyncio.run(run()) is None
