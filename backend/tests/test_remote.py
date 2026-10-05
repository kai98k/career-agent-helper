"""雲端 agent 的轉接層（Day 21）。不連雲端。

event 的格式照 Agent Runtime 的 stream_query 實際回傳的 dict 寫。
"""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent.remote import _absorb, _is_not_found
from app.agent.runner import AgentError, AgentTimeout, AgentTurn


def _ev(**kw) -> dict:
    return kw


def test_error_event_becomes_an_exception():
    """Day 19：雲端把 404 包成 event，不檢查就變成「成功但沒有回覆」。"""
    turn = AgentTurn(text="")
    with pytest.raises(AgentError, match="404"):
        _absorb(turn, _ev(error_code="ClientError", error_message="404 NOT_FOUND. Publisher model ..."))


def test_tool_call_then_reply():
    turn = AgentTurn(text="")
    _absorb(turn, _ev(
        content={"parts": [{"function_call": {"name": "verify_evidence", "args": {}}}]},
        usage_metadata={"prompt_token_count": 100, "total_token_count": 120},
    ))
    _absorb(turn, _ev(
        content={"parts": [{"text": "分析如下", "thought": None}]},
        usage_metadata={"prompt_token_count": 200, "total_token_count": 260},
        custom_metadata={"unverified_quotes": ["技能：Git"]},
    ))
    assert turn.tool_calls == ["verify_evidence"]
    assert turn.text == "分析如下"
    assert turn.unverified_quotes == ["技能：Git"]
    assert (turn.llm_calls, turn.total_tokens) == (2, 380)


def test_thought_parts_are_not_shown():
    turn = AgentTurn(text="")
    _absorb(turn, _ev(content={"parts": [{"text": "我在想…", "thought": True}, {"text": "答案"}]}))
    assert turn.text == "答案"


def test_stopped_reply_moves_to_stopped():
    turn = AgentTurn(text="")
    _absorb(turn, _ev(content={"parts": [{"text": "已攔下"}]}, custom_metadata={"stopped": "leak"}))
    assert (turn.text, turn.stopped) == ("", "已攔下")


def test_not_found_codes():
    """拿別人的 session，Agent Runtime 回的是 400 不是 404（Day 21 實測）。"""
    class E(Exception):
        def __init__(self, code):
            self.code = code
    assert _is_not_found(E(400)) and _is_not_found(E(404))
    assert not _is_not_found(E(500)) and not _is_not_found(Exception())


class _Stub:
    """假的 agent：exists 都說有，send 丟指定的例外。"""

    def __init__(self, exc):
        self.exc = exc

    async def exists(self, user_id, session_id):
        return True

    async def send(self, user_id, session_id, message):
        raise self.exc

    async def purge_expired(self, ttl_hours=None):
        return 0


@pytest.mark.parametrize("exc, status", [(AgentTimeout("180 秒"), 504), (AgentError("404 NOT_FOUND"), 502)])
def test_agent_failures_become_http_errors(monkeypatch, exc, status):
    monkeypatch.setattr(main, "_agent", _Stub(exc))
    r = TestClient(main.app).post(
        "/agent/sessions/s1/messages", json={"message": "hi"}, headers={"X-Session-Token": "t"}
    )
    assert r.status_code == status
    assert r.json()["detail"]


def test_text_next_to_a_tool_call_is_kept():
    turn = AgentTurn(text="")
    _absorb(turn, _ev(content={"parts": [{"text": "計畫如下：第 1 週 SQL"},
                                         {"function_call": {"name": "validate_learning_plan", "args": {}}}]}))
    _absorb(turn, _ev(content={"parts": [{"text": "計畫已通過檢核"}]}))
    assert turn.text == "計畫如下：第 1 週 SQL\n\n計畫已通過檢核"


def test_stopped_reply_drops_earlier_text_too():
    turn = AgentTurn(text="")
    _absorb(turn, _ev(content={"parts": [{"text": "前面那段"},
                                         {"function_call": {"name": "verify_evidence", "args": {}}}]}))
    _absorb(turn, _ev(content={"parts": [{"text": "已攔下"}]}, custom_metadata={"stopped": "leak"}))
    assert (turn.text, turn.stopped) == ("", "已攔下")


def test_clean_error_removes_the_echoed_resume():
    """Day 21 實測：ttl 太短的錯誤訊息，把整個請求（含履歷全文）原樣附在後面。"""
    from app.agent.remote import clean_error

    raw = ("400 INVALID_ARGUMENT. `ttl` must be at least 24 hours.\nRequest Data: "
           "{'state': {'resume_text': '陳柏宇\n後端工程師 / 1 年經驗\nEmail: boyu.chen@example.invalid'}}")
    out = clean_error(raw)
    assert "ttl" in out
    assert "陳柏宇" not in out and "example.invalid" not in out
    assert len(clean_error("x" * 1000)) <= 300
