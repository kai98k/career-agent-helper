"""跑 agent 並保存對話狀態（Day 16）。

履歷放進 session state 而不是每次都塞進訊息裡，有兩個理由：
一是省 token，二是工具取用的永遠是同一份確認過的文字，
agent 沒有機會在傳遞過程中「順手改一下」。

本機用 InMemorySessionService。部署到 Agent Runtime 之後改接受管 Sessions，
換的只有這個檔案裡的一行。
"""

import time
from dataclasses import dataclass, field

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from app.agent.agent import build_agent
from app.agent.tools import STATE_RESUME

APP_NAME = "career-agent-helper"


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


class AgentSession:
    """包一層，讓呼叫端不用碰 ADK 的 Runner 細節。"""

    def __init__(
        self,
        *,
        session_service: BaseSessionService | None = None,
        agent: LlmAgent | None = None,
    ):
        self._agent = agent or build_agent()
        self._sessions = session_service or InMemorySessionService()
        self._runner = Runner(
            app_name=APP_NAME, agent=self._agent, session_service=self._sessions
        )

    async def start(self, user_id: str, resume_text: str, session_id: str | None = None):
        """開一個新 session，把確認過的履歷放進 state。"""
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
                turn.text = "".join(p.text or "" for p in event.content.parts)

        turn.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return turn

    async def state(self, user_id: str, session_id: str) -> dict:
        s = await self._sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        return dict(s.state) if s else {}

    async def delete(self, user_id: str, session_id: str) -> None:
        """Day 17 要的刪除。履歷是高敏感個資，要能真的刪掉。"""
        await self._sessions.delete_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
