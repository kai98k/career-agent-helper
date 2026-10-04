"""打 Cloud Run 上的 agent，跟 query_agent.py 做一樣的事（Day 20）。

    cd backend
    .venv/Scripts/python.exe scripts/query_cloud_run.py

需要 .env 的 CLOUD_RUN_URL（deploy_cloud_run.py 印出來的服務網址）。

Cloud Run 上跑的是 adk api_server，是一般的 HTTP API：
- 沒帶身分的請求要被擋掉（部署時加了 --no-allow-unauthenticated）
- 帶身分用的是 gcloud 給的 identity token
- session 存在 Day 19 的 Agent Runtime Sessions，所以用 Agent Runtime 的 API 也要讀得到
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.agent.tools import STATE_RESUME  # noqa: E402

APP = "career_advisor"
USER = "day20-smoke"
RESUME = (ROOT / "data/resumes/sample-backend-1y.txt").read_text(encoding="utf-8")
JOB = (ROOT / "data/jobs/sample-job-backend-junior.txt").read_text(encoding="utf-8")
MESSAGE = "我想應徵下面這個職缺，幫我看看履歷跟它的落差。\n\n" + JOB


def _token() -> str:
    gcloud = "gcloud.cmd" if os.name == "nt" else "gcloud"
    return subprocess.run(
        [gcloud, "auth", "print-identity-token"], capture_output=True, text=True, check=True
    ).stdout.strip()


def call(base: str, method: str, path: str, body=None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(base + path, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def main() -> None:
    base = os.environ.get("CLOUD_RUN_URL", "").rstrip("/")
    if not base:
        raise SystemExit("請在 .env 設定 CLOUD_RUN_URL")

    try:
        call(base, "GET", "/list-apps")
        print("沒帶身分：竟然通過了，檢查 --no-allow-unauthenticated")
    except urllib.error.HTTPError as e:
        print(f"沒帶身分：{e.code}")

    token = _token()
    started = time.perf_counter()
    s = call(base, "POST", f"/apps/{APP}/users/{USER}/sessions", {"state": {STATE_RESUME: RESUME}}, token)
    print(f"建立 session：{time.perf_counter() - started:.1f} 秒  id={s['id']}")

    try:
        started = time.perf_counter()
        events = call(base, "POST", "/run", {
            "app_name": APP, "user_id": USER, "session_id": s["id"],
            "new_message": {"role": "user", "parts": [{"text": MESSAGE}]},
        }, token)
        secs = time.perf_counter() - started
        calls = [p["functionCall"]["name"] for e in events for p in e.get("content", {}).get("parts", []) if "functionCall" in p]
        tokens = sum((e.get("usageMetadata") or {}).get("totalTokenCount", 0) for e in events)
        final = events[-1]
        if final.get("errorCode"):
            raise RuntimeError(f"agent 回報錯誤：{final.get('errorMessage')}")
        text = "".join(p.get("text", "") for p in final["content"]["parts"])
        print(f"第 1 輪：{secs:.1f} 秒 / {tokens} tokens / {len(calls)} 次工具呼叫 {calls}")
        print(f"  custom_metadata={final.get('customMetadata')}")
        print(f"  回覆開頭：{text[:120]!r}")

        # 同一個 session，從 Agent Runtime 那邊讀，確認兩條路用的是同一個存放處
        engine = os.environ.get("AGENT_ENGINE_NAME")
        if engine:
            import asyncio

            import vertexai

            from app.config import get_settings

            async def peek():
                client = vertexai.Client(project=get_settings().require_project_id(), location="asia-east1")
                remote = client.agent_engines.get(name=engine)
                got = await remote.async_get_session(user_id=USER, session_id=s["id"])
                return len(got.get("events", [])), list(got.get("state", {}))

            n, keys = asyncio.run(peek())
            print(f"從 Agent Runtime 讀同一個 session：{n} 個 event，state={keys}")
    finally:
        call(base, "DELETE", f"/apps/{APP}/users/{USER}/sessions/{s['id']}", token=token)
        print("session 已刪除")


if __name__ == "__main__":
    main()
