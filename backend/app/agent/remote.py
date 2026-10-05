"""讓 FastAPI 改打 Agent Runtime 上的 agent（Day 21）。

介面跟本機的 AgentSession 一樣（start / send / exists / delete / purge_expired），
main.py 用 AGENT_BACKEND 決定用哪一個，端點不用改。

這一層是 Day 20 說的「門口」：
- user_id 一律由 main.py 從使用者的憑證算出來，不讓瀏覽器自己填。
  Agent Runtime 會照 user_id 隔離 session（Day 21 實測：換一個 user_id 讀不到、刪不掉），
  但它相信呼叫端給的 user_id，所以這個值怎麼來的，是這一層的責任。
- 雲端出錯時不會丟例外，而是送一個帶 error_code 的 event（Day 19），這裡轉成例外。
- 冷啟動要一分鐘（Day 20），等太久要有上限，不能讓請求永遠掛著。
"""

import asyncio
import time
from types import SimpleNamespace

from app.agent.runner import AgentError, AgentTimeout, AgentTurn
from app.agent.tools import STATE_RESUME
from app.config import get_settings

# 一句話最久等多久。Day 20 量到冷啟動：建 session 36.5 秒 + 第一個回覆 29.9 秒，
# 加上第一輪可能叫 9 次工具（Day 19，24 秒），抓 3 分鐘。
SEND_TIMEOUT_S = 180


def clean_error(msg: str) -> str:
    """雲端的錯誤訊息會把整個請求原樣附上，包括 state 裡的履歷全文（Day 21 實測）。

    這段字串會變成 HTTP 回應的 detail，之後也可能進 log（Day 23），
    所以「Request Data」之後全部切掉，再限制長度。
    """
    msg = str(msg)
    cuts = [i for i in (msg.find("Request Data"), msg.find("resume_text")) if i != -1]
    if cuts:
        msg = msg[: min(cuts)] + "…（後面是請求內容，已移除）"
    return msg[:300]


def _is_not_found(e: Exception) -> bool:
    # 拿別人的 session、或 session 不存在，Agent Runtime 回的都是
    # 400 "Reasoning Engine Execution failed"，不是 404（Day 21 實測）。
    code = getattr(e, "code", None)
    return code in (400, 404)


class RemoteAgentSession:
    def __init__(self, engine_name: str | None = None):
        import vertexai

        s = get_settings()
        name = engine_name or s.agent_engine_name
        if not name:
            raise RuntimeError("AGENT_BACKEND=runtime 需要 .env 的 AGENT_ENGINE_NAME")
        # client 要存起來：寫成 vertexai.Client(...).agent_engines.get(...) 的話，
        # 暫時的 client 被 GC 回收，底層連線跟著關掉（Day 19 踩過）。
        self._client = vertexai.Client(project=s.require_project_id(), location=s.agent_runtime_location)
        self._remote = self._client.agent_engines.get(name=name)
        self._ttl = f"{int(s.session_ttl_hours * 3600)}s"

    async def start(self, user_id: str, resume_text: str, session_id: str | None = None):
        # 不給 ttl 的話，受管 session 預設放一年（Day 21 用 REST API 查 expireTime 才看到）。
        # 跟本機一樣放 24 小時。不一樣的是：本機從「最後一次動作」算，這裡從建立開始算。
        # 另外，ttl 最短就是 24 小時，給 3600s 會被拒絕（Day 21 實測）。
        try:
            s = await self._remote.async_create_session(
                user_id=user_id, state={STATE_RESUME: resume_text}, ttl=self._ttl
            )
        except Exception as e:
            raise AgentError(clean_error(e)) from None  # from None：不把帶履歷的原始例外接在後面
        return SimpleNamespace(id=s["id"])

    async def send(self, user_id: str, session_id: str, message: str) -> AgentTurn:
        started = time.perf_counter()
        turn = AgentTurn(text="")
        try:
            async with asyncio.timeout(SEND_TIMEOUT_S):
                async for ev in self._remote.async_stream_query(
                    user_id=user_id, session_id=session_id, message=message
                ):
                    _absorb(turn, ev)
        except TimeoutError as e:
            raise AgentTimeout(f"超過 {SEND_TIMEOUT_S} 秒沒有回完") from e
        except AgentError:
            raise
        except Exception as e:
            raise AgentError(clean_error(e)) from None
        turn.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return turn

    async def exists(self, user_id: str, session_id: str) -> bool:
        try:
            await self._remote.async_get_session(user_id=user_id, session_id=session_id)
            return True
        except Exception as e:
            if _is_not_found(e):
                return False
            raise AgentError(clean_error(e)) from None

    async def delete(self, user_id: str, session_id: str) -> bool:
        if not await self.exists(user_id, session_id):
            return False
        try:
            await self._remote.async_delete_session(user_id=user_id, session_id=session_id)
        except Exception as e:
            raise AgentError(clean_error(e)) from None
        return True

    async def purge_expired(self, ttl_hours: float | None = None) -> int:
        """受管 session 建立時就帶了 ttl，平台自己會刪，這裡不用做事。"""
        return 0


def _absorb(turn: AgentTurn, ev: dict) -> None:
    """把一個雲端 event（dict）累加進 AgentTurn，跟本機 runner 讀 Event 的邏輯對齊。"""
    if ev.get("error_code") or ev.get("errorCode"):
        raise AgentError(clean_error(ev.get("error_message") or ev.get("errorMessage") or "agent 回報錯誤"))

    u = ev.get("usage_metadata") or {}
    if u:
        turn.prompt_tokens += u.get("prompt_token_count") or 0
        turn.thought_tokens += u.get("thoughts_token_count") or 0
        turn.output_tokens += u.get("candidates_token_count") or 0
        turn.total_tokens += u.get("total_token_count") or 0
        turn.llm_calls += 1

    parts = (ev.get("content") or {}).get("parts") or []
    calls = [p["function_call"]["name"] for p in parts if p.get("function_call")]
    turn.tool_calls.extend(calls)
    text = "".join(p.get("text") or "" for p in parts if not p.get("thought"))
    if not text:
        return
    # 模型會在呼叫工具的同一則回應裡先寫一段（例如整份計畫），最後一則只剩
    # 「計畫已通過檢核」。只留最後一則的話，使用者看不到計畫（Day 21 實測）。
    # 所以這一輪所有要給人看的文字都接起來。
    turn.text = f"{turn.text}\n\n{text}" if turn.text else text
    if not calls:
        meta = ev.get("custom_metadata") or {}
        turn.unverified_quotes = meta.get("unverified_quotes", [])
        if meta.get("stopped"):
            # 被擋下時連前面的文字一起不給：洩漏也可能在前面那段
            turn.stopped, turn.text = text, ""
