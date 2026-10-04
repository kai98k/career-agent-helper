"""掛在 agent 上的兩道關卡（Day 19 從 runner 搬過來）。

Day 15 的呼叫次數上限放在 runner 的 RunConfig，Day 18 的 guard 也在 runner 裡。
本機沒問題，因為本機是 runner.py 在跑 agent。
部署到 Agent Runtime 之後，跑 agent 的是平台的 AdkApp：
- runner.py 根本不會被呼叫
- RunConfig 變成「呼叫端」每次自己帶的參數，不帶就是 ADK 預設的 500 次

所以必須成立的規則，要跟著 agent 走。ADK 的 callback 會在每次呼叫模型的前後執行，
本機跟雲端都一樣。

結果透過 LlmResponse.custom_metadata 帶出去，它會跟著 event 一路傳到呼叫端，
本機的 runner 跟雲端的 stream_query 都拿得到。
"""

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from app.agent import guard
from app.agent.tools import STATE_RESUME

# 一次對話（一個 invocation）最多呼叫模型幾次（Day 15）。
# ADK 預設是 500，對一個專案花費上限 $10 的作品來說等於沒有上限。
# 第一版設 8，實測 agent 一條要求驗證一次，8 次全用在 verify_evidence，
# 還沒回覆使用者就被中止。實測最多 8 次驗證 + 1 次回覆，再留修正計畫的空間。
MAX_LLM_CALLS = 12

LIMIT_NOTICE = f"這一輪呼叫模型超過 {MAX_LLM_CALLS} 次，已中止。"
LEAK_NOTICE = "這一輪的回覆裡出現了系統內部的指示，已攔下。履歷裡可能有要求 AI 輸出設定的文字。"

# temp: 開頭的 state 只活在這一次 invocation，下一句話重新算
_CALLS = "temp:llm_calls"


def _notice(text: str, reason: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        custom_metadata={"stopped": reason},
    )


def limit_llm_calls(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """超過上限就不呼叫模型，直接回一段說明。回傳 None 表示照常呼叫。"""
    n = callback_context.state.get(_CALLS, 0) + 1
    callback_context.state[_CALLS] = n
    if n > MAX_LLM_CALLS:
        return _notice(LIMIT_NOTICE, "llm_call_limit")
    return None


def _user_texts(callback_context: CallbackContext) -> list[str]:
    texts = [
        "".join(p.text or "" for p in e.content.parts)
        for e in callback_context.session.events
        if e.author == "user" and e.content and e.content.parts
    ]
    current = callback_context.user_content
    if current and current.parts:
        texts.append("".join(p.text or "" for p in current.parts))
    return texts


def guard_reply(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """只檢查要給使用者看的文字回覆，呼叫工具的那幾次不管。"""
    content = llm_response.content
    if llm_response.partial or not content or not content.parts:
        return None
    if any(p.function_call for p in content.parts):
        return None

    text = "".join(p.text or "" for p in content.parts if not p.thought)
    if not text:
        return None

    meta = dict(llm_response.custom_metadata or {})
    if guard.leaked(text):
        # 洩漏就整段換掉。換掉之後存進 session 的也是說明，不是洩漏的原文，
        # 下一輪模型看歷史時不會再看到自己吐出來的指示。
        # usage_metadata 留著，token 還是要算。
        llm_response.content = types.Content(role="model", parts=[types.Part(text=LEAK_NOTICE)])
        meta["stopped"] = "leak"
    else:
        resume = callback_context.state.get(STATE_RESUME, "")
        unverified = guard.unverified_quotes(text, resume, _user_texts(callback_context))
        if unverified:
            meta["unverified_quotes"] = unverified

    llm_response.custom_metadata = meta or None
    return llm_response
