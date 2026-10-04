"""跑 agent 並保存對話狀態（Day 16）。

履歷放進 session state，工具取用的永遠是同一份確認過的文字，
agent 沒有機會在傳遞過程中「順手改一下」。
這樣做**沒有省 token**：instruction 裡的 {resume_text} 每次呼叫模型都會從 state 填進去。
省的是「履歷只有一個來源」。

本機用 DatabaseSessionService + SQLite，服務重開對話還在。
部署到 Agent Runtime 之後改接受管 Sessions，換的只有 make_session_service。

Day 17：誰能碰這個 session、放多久、刪掉之後是不是真的沒了。

Day 19：呼叫次數上限跟回覆檢查搬到 agent 的 callback（app/agent/callbacks.py），
因為部署之後跑 agent 的不是這個檔案。這裡只負責把結果讀出來。
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from app.agent.agent import build_agent
from app.agent.callbacks import MAX_LLM_CALLS  # noqa: F401（舊的 import 路徑）
from app.agent.tools import STATE_RESUME
from app.config import get_settings

APP_NAME = "career-agent-helper"


def make_session_service(url: str | None = None) -> BaseSessionService:
    url = get_settings().session_db_url if url is None else url
    if not url:
        return InMemorySessionService()

    # 延後 import：沒裝 google-adk[db] 也能用記憶體版跑
    from google.adk.sessions import DatabaseSessionService

    # SQLite 不會自己建資料夾
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return DatabaseSessionService(db_url=url)

    Path(url.removeprefix(prefix)).parent.mkdir(parents=True, exist_ok=True)
    svc = DatabaseSessionService(db_url=url)

    # SQLite 刪資料只是把 page 標成可重用，內容原封不動留在檔案裡（Day 17 實測）。
    # secure_delete 會在刪除時把那些位置寫成 0。
    from sqlalchemy import event

    def _secure_delete(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA secure_delete=ON")
        cur.close()

    event.listen(svc.db_engine.sync_engine, "connect", _secure_delete)
    return svc


def new_owner_token() -> str:
    """開 session 時發給呼叫端的憑證，只回傳這一次，伺服器不存原文。

    Day 16 以前 user_id 是呼叫端自己填的，誰自稱 alice 就能刪 alice 的 session。
    Day 21 接上真正的身分驗證之後，owner 改成登入身分，這一段就退場。
    """
    return secrets.token_urlsafe(32)


def owner_of(token: str) -> str:
    """從憑證算出 session 的 user_id。資料庫裡只有雜湊，拿到資料庫也還原不出憑證。"""
    return "anon-" + hashlib.sha256(token.encode()).hexdigest()[:32]


@dataclass
class AgentTurn:
    text: str
    tool_calls: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    thought_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    elapsed_ms: int = 0
    stopped: str | None = None  # 被呼叫上限或 guard 擋下時，填給使用者看的說明
    # Day 18：回覆裡用「」引用、但在履歷跟使用者訊息裡都找不到的句子
    unverified_quotes: list[str] = field(default_factory=list)


class AgentSession:
    """包一層，讓呼叫端不用碰 ADK 的 Runner 細節。"""

    def __init__(
        self,
        *,
        session_service: BaseSessionService | None = None,
        agent: LlmAgent | None = None,
        use_guard: bool = True,
    ):
        self._agent = agent or build_agent(use_guard=use_guard)
        self._sessions = session_service or make_session_service()
        self._runner = Runner(
            app_name=APP_NAME, agent=self._agent, session_service=self._sessions
        )

    async def start(self, user_id: str, resume_text: str, session_id: str | None = None):
        """開一個新 session，把確認過的履歷放進 state。

        順便清掉過期的。沒有排程器，就在有人進來時清，量小的時候夠用。
        """
        await self.purge_expired()
        s = await self._sessions.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state={STATE_RESUME: resume_text},
        )
        return s

    async def send(self, user_id: str, session_id: str, message: str) -> AgentTurn:
        started = time.perf_counter()
        turn = AgentTurn(text="")
        content = types.Content(role="user", parts=[types.Part(text=message)])

        async for event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            if event.usage_metadata:
                u = event.usage_metadata
                turn.prompt_tokens += u.prompt_token_count or 0
                turn.thought_tokens += u.thoughts_token_count or 0
                turn.output_tokens += u.candidates_token_count or 0
                turn.total_tokens += u.total_token_count or 0
                turn.llm_calls += 1

            for call in event.get_function_calls() or []:
                turn.tool_calls.append(call.name)

            if event.is_final_response() and event.content and event.content.parts:
                turn.text = "".join(p.text or "" for p in event.content.parts if not p.thought)
                meta = event.custom_metadata or {}
                turn.unverified_quotes = meta.get("unverified_quotes", [])
                if meta.get("stopped"):
                    # 被擋下時，文字是 callback 換上的說明。說明放 stopped，不當成答案。
                    turn.stopped, turn.text = turn.text, ""

        turn.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return turn

    async def exists(self, user_id: str, session_id: str) -> bool:
        s = await self._sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        return s is not None

    async def events(self, user_id: str, session_id: str) -> list:
        """給評估用：看工具實際被傳了什麼參數、回了什麼（Day 18）。"""
        s = await self._sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        return list(s.events) if s else []

    async def state(self, user_id: str, session_id: str) -> dict:
        s = await self._sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        return dict(s.state) if s else {}

    async def delete(self, user_id: str, session_id: str) -> bool:
        """履歷是高敏感個資，要能真的刪掉。回傳有沒有刪到東西。

        ADK 的 delete_session 找不到也不會報錯，不先查一次，
        刪別人的、刪不存在的、刪成功的，看起來都一樣。
        """
        if not await self.exists(user_id, session_id):
            return False
        await self._sessions.delete_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        return True

    async def purge_expired(self, ttl_hours: float | None = None) -> int:
        """刪掉超過保留期限沒動過的 session，回傳刪了幾個。"""
        ttl = get_settings().session_ttl_hours if ttl_hours is None else ttl_hours
        cutoff = time.time() - ttl * 3600
        listed = await self._sessions.list_sessions(app_name=APP_NAME)
        expired = [s for s in listed.sessions if s.last_update_time < cutoff]
        for s in expired:
            await self._sessions.delete_session(
                app_name=APP_NAME, user_id=s.user_id, session_id=s.id
            )
        return len(expired)
