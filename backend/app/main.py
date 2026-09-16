"""FastAPI 進入點。Day 04 起逐步長出履歷分析的端點。"""

from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title="Career Agent Helper", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "env": s.app_env,
        "location": s.location,
        "model": s.model,
        "project_configured": bool(s.project_id),
    }
