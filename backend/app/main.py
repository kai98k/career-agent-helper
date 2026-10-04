"""FastAPI 進入點。只管路由與 HTTP 狀態碼轉換，邏輯都在 services 底下。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field

from app import prompts
from app.agent.runner import AgentSession, new_owner_token, owner_of
from app.config import get_settings
from app.schemas.clarify import Answer
from app.schemas.report import AnalysisReport
from app.services import pipeline, resources
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, PdfExtractResponse
from app.services.analyzer import AnalyzerError, analyze
from app.services.llm import LlmError
from app.services.pdf import PdfExtractError, extract_text

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 服務起來時先清一次過期的 session，不然沒人來就永遠不會清（Day 17）
    await _agent.purge_expired()
    yield


app = FastAPI(title="Career Agent Helper", version="0.2.0", lifespan=lifespan)


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
    do_clarify: bool = True
    answers: list[Answer] = Field(default_factory=list, max_length=10)


@app.get("/resources")
def list_resources() -> list[dict]:
    """只回人工核實過的資源，前端用 id 對回計畫裡的 resource_ids。"""
    return [r.model_dump() for r in resources.verified_only()]


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
            do_clarify=req.do_clarify,
            answers=req.answers,
        )
    except LlmError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e


# 路徑 B：agent。跟路徑 A 並存，Day 29 要拿兩者比較，不能拆掉任何一條。
_agent = AgentSession()


class StartSessionRequest(BaseModel):
    resume_text: str = Field(min_length=20, max_length=20_000)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)


# 找不到跟不是你的，回一樣的 404。
# 回 403 等於告訴對方「這個 session id 存在」。
_NOT_FOUND = HTTPException(status_code=404, detail="找不到這個 session，可能已過期或被刪除")


@app.post("/agent/sessions")
async def start_agent_session(req: StartSessionRequest) -> dict:
    """token 只在這裡出現一次，之後每個請求都要帶 X-Session-Token。"""
    token = new_owner_token()
    s = await _agent.start(owner_of(token), req.resume_text)
    return {"session_id": s.id, "token": token}


@app.post("/agent/sessions/{session_id}/messages")
async def send_to_agent(
    session_id: str,
    req: MessageRequest,
    x_session_token: str = Header(min_length=1),
) -> dict:
    owner = owner_of(x_session_token)
    if not await _agent.exists(owner, session_id):
        raise _NOT_FOUND
    try:
        turn = await _agent.send(owner, session_id, req.message)
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
        "stopped": turn.stopped,
        # 回覆裡用「」引用、但履歷跟使用者的訊息裡都找不到的句子，給畫面標示用（Day 18）
        "unverified_quotes": turn.unverified_quotes,
    }


@app.delete("/agent/sessions/{session_id}", status_code=204)
async def delete_agent_session(
    session_id: str, x_session_token: str = Header(min_length=1)
) -> Response:
    """履歷是高敏感個資，刪除要是一個真的端點，不是「之後再說」。"""
    if not await _agent.delete(owner_of(x_session_token), session_id):
        raise _NOT_FOUND
    return Response(status_code=204)


# 靜態前端掛在最後：mount 在 "/" 會吃掉所有沒被上面路由接走的路徑，
# 所以一定要放在全部 API 路由定義之後。
# main.py 在 backend/app/，web/ 在專案根目錄，所以往上兩層再進 web。
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
