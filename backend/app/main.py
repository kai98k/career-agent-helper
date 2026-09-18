"""FastAPI 進入點。只管路由與 HTTP 狀態碼轉換，邏輯都在 services 底下。"""

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field

from app import prompts
from app.agent.runner import AgentSession
from app.config import get_settings
from app.schemas.report import AnalysisReport
from app.services import pipeline
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, PdfExtractResponse
from app.services.analyzer import AnalyzerError, analyze
from app.services.llm import LlmError
from app.services.pdf import PdfExtractError, extract_text

app = FastAPI(title="Career Agent Helper", version="0.2.0")


@app.get("/healthz")
def healthz() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "env": s.app_env,
        "location": s.location,
        "model": s.model,
        "project_configured": bool(s.project_id),
        "prompts": sorted(prompts.REGISTRY),
    }


@app.get("/prompts")
def list_prompts() -> list[dict]:
    """讓前端可以列出有哪些 prompt 可選，也方便之後做版本比較。"""
    return [
        {"key": k, "name": p.name, "version": p.version, "description": p.description}
        for k, p in sorted(prompts.REGISTRY.items())
    ]


@app.post("/extract/pdf", response_model=PdfExtractResponse)
async def extract_pdf(file: UploadFile = File(...)) -> PdfExtractResponse:
    """抽取 PDF 文字，回給使用者確認。

    刻意不直接接上分析：pypdf 對版面複雜的履歷常會打亂欄位順序，
    使用者需要先看到抽出來的東西長怎樣。
    """
    s = get_settings()
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail=f"只接受 PDF，收到 {file.content_type}")
    try:
        result = extract_text(
            await file.read(),
            max_bytes=s.max_upload_mb * 1_048_576,
            max_pages=s.max_pdf_pages,
        )
    except PdfExtractError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e

    return PdfExtractResponse(
        text=result.text,
        page_count=result.page_count,
        char_count=result.char_count,
        empty_pages=result.empty_pages,
        warning=result.warning,
    )


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_resume(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return analyze(req.resume_text, req.job_text, req.prompt)
    except AnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e


class FullAnalyzeRequest(BaseModel):
    resume_text: str = Field(min_length=20, max_length=20_000)
    job_text: str | None = Field(default=None, max_length=20_000)
    weekly_hours: float = Field(default=10.0, gt=0, le=60)
    do_rewrite: bool = True
    do_plan: bool = True


@app.post("/analyze/full", response_model=AnalysisReport)
def analyze_full(req: FullAnalyzeRequest) -> AnalysisReport:
    """路徑 A：固定流程。順序寫死，成本可預測。"""
    try:
        return pipeline.run(
            req.resume_text,
            req.job_text,
            do_rewrite=req.do_rewrite,
            do_plan=req.do_plan,
            weekly_hours=req.weekly_hours,
        )
    except LlmError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e


# 路徑 B：agent。跟路徑 A 並存，Day 29 要拿兩者比較，不能拆掉任何一條。
_agent = AgentSession()


class StartSessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    resume_text: str = Field(min_length=20, max_length=20_000)


class MessageRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4_000)


@app.post("/agent/sessions")
async def start_agent_session(req: StartSessionRequest) -> dict:
    s = await _agent.start(req.user_id, req.resume_text)
    return {"session_id": s.id, "user_id": req.user_id}


@app.post("/agent/sessions/{session_id}/messages")
async def send_to_agent(session_id: str, req: MessageRequest) -> dict:
    try:
        turn = await _agent.send(req.user_id, session_id, req.message)
    except LlmError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    return {
        "text": turn.text,
        "tool_calls": turn.tool_calls,
        "usage": {
            "prompt_tokens": turn.prompt_tokens,
            "thought_tokens": turn.thought_tokens,
            "output_tokens": turn.output_tokens,
            "total_tokens": turn.total_tokens,
            "llm_calls": turn.llm_calls,
        },
        "elapsed_ms": turn.elapsed_ms,
    }


@app.delete("/agent/sessions/{session_id}", status_code=204)
async def delete_agent_session(session_id: str, user_id: str) -> None:
    """履歷是高敏感個資，刪除要是一個真的端點，不是「之後再說」。"""
    await _agent.delete(user_id, session_id)


# 靜態前端掛在最後：mount 在 "/" 會吃掉所有沒被上面路由接走的路徑，
# 所以一定要放在全部 API 路由定義之後。
# main.py 在 backend/app/，web/ 在專案根目錄，所以往上兩層再進 web。
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
