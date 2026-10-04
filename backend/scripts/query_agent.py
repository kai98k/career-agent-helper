"""打部署好的 agent 一次，確認雲端跟本機的行為一樣（Day 19）。

    cd backend
    .venv/Scripts/python.exe scripts/query_agent.py

需要 .env 裡的 AGENT_ENGINE_NAME（deploy_agent.py 印出來的那串）。

不是只看「有沒有回話」，而是確認幾件上雲端之後可能悄悄壞掉的事：
- session state 裡的履歷，工具拿不拿得到（verify_evidence 要回 exact）
- 資源清單有沒有一起打包上去（lookup_resources 不能報錯）
- callback 有沒有跟著 agent 上去（回覆的 custom_metadata）
用完就刪 session，履歷不留在雲端（Day 17）。
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

import vertexai  # noqa: E402

from app.agent.tools import STATE_RESUME  # noqa: E402
from app.config import get_settings  # noqa: E402

USER = "day19-smoke"
RAW = "--raw" in sys.argv  # 印出每個原始 event，雲端靜靜失敗的時候用
RESUME = (ROOT / "data/resumes/sample-backend-1y.txt").read_text(encoding="utf-8")
JOB = (ROOT / "data/jobs/sample-job-backend-junior.txt").read_text(encoding="utf-8")
MESSAGES = [
    "我想應徵下面這個職缺，幫我看看履歷跟它的落差。\n\n" + JOB,
    "請幫我查一下 SQL 跟 Docker 有沒有推薦的學習資源。",
]


async def ask(remote, session_id: str, message: str) -> None:
    started = time.perf_counter()
    calls, tokens, final, meta = [], 0, "", {}
    async for ev in remote.async_stream_query(user_id=USER, session_id=session_id, message=message):
        if RAW:
            print("  RAW", json.dumps(ev, ensure_ascii=False, default=str)[:600])
        # 模型或工具出錯時，雲端不會丟例外，而是送一個帶 error_code 的 event。
        # 不檢查的話，看起來就是「成功，但沒有回覆」（Day 19 就這樣被騙了一次）。
        if ev.get("error_code") or ev.get("errorCode"):
            raise RuntimeError(f"agent 回報錯誤：{ev.get('error_message') or ev.get('errorMessage')}")
        parts = (ev.get("content") or {}).get("parts") or []
        for p in parts:
            if "function_call" in p:
                calls.append((p["function_call"]["name"], p["function_call"].get("args")))
            if "function_response" in p:
                resp = p["function_response"]["response"]
                print(f"  ← {p['function_response']['name']}: {json.dumps(resp, ensure_ascii=False)[:200]}")
            if p.get("text") and not p.get("thought"):
                final = p["text"]
        tokens += (ev.get("usage_metadata") or {}).get("total_token_count", 0)
        if ev.get("custom_metadata"):
            meta = ev["custom_metadata"]
    secs = time.perf_counter() - started
    for name, args in calls:
        print(f"  → {name}: {json.dumps(args, ensure_ascii=False)[:200]}")
    print(f"  {secs:.1f} 秒 / {tokens} tokens / custom_metadata={meta}")
    print(f"  回覆開頭：{final[:200]!r}")


async def main() -> None:
    name = os.environ.get("AGENT_ENGINE_NAME")
    if not name:
        raise SystemExit("請在 .env 設定 AGENT_ENGINE_NAME")
    s = get_settings()
    location = os.environ.get("AGENT_RUNTIME_LOCATION", "asia-east1")
    client = vertexai.Client(project=s.require_project_id(), location=location)
    remote = client.agent_engines.get(name=name)

    started = time.perf_counter()
    session = await remote.async_create_session(user_id=USER, state={STATE_RESUME: RESUME})
    sid = session["id"]
    print(f"建立 session：{time.perf_counter() - started:.1f} 秒")
    try:
        for i, msg in enumerate(MESSAGES, 1):
            print(f"\n=== 第 {i} 輪")
            await ask(remote, sid, msg)
    finally:
        await remote.async_delete_session(user_id=USER, session_id=sid)
        print("\nsession 已刪除")


if __name__ == "__main__":
    asyncio.run(main())
