"""把 Day 03 那支腳本搬進來，加上服務化需要的三件事：
逾時、錯誤轉換、用量回報。
"""

import time

from google import genai
from google.genai import errors, types

from app import prompts
from app.config import get_settings
from app.schemas.analysis import AnalyzeResponse, Usage

class AnalyzerError(RuntimeError):
    """把 SDK 的例外收斂成一種，讓端點只需要處理一個型別。"""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _client() -> genai.Client:
    """每次請求都重建 client。

    Client 本身很輕，重建的成本遠低於「憑證過期但物件還活著」的除錯成本。
    等 Day 22 量到真實延遲之後，再決定要不要改成模組層級的單例。
    """
    s = get_settings()
    return genai.Client(
        vertexai=True,
        project=s.require_project_id(),
        location=s.location,
        http_options=types.HttpOptions(api_version="v1", timeout=60_000),
    )


def analyze(
    resume_text: str,
    job_text: str | None = None,
    prompt_key: str = prompts.DEFAULT,
) -> AnalyzeResponse:
    s = get_settings()
    try:
        tmpl = prompts.get(prompt_key)
    except KeyError as e:
        raise AnalyzerError(str(e), status_code=400) from e
    prompt = tmpl.render(resume=resume_text, job=job_text)

    config = types.GenerateContentConfig(
        # 沒有要用工具，關掉 AFC 少一層看不見的迴圈，也少一則警告。
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    # client 必須存成區域變數。寫成 _client().models.generate_content(...) 的話，
    # 暫時物件沒有任何人持有，會在請求送出前被 GC 回收並關掉底層的 httpx 連線，
    # 得到 RuntimeError: Cannot send a request, as the client has been closed.
    client = _client()

    started = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=s.model, contents=prompt, config=config
        )
    except errors.ClientError as e:
        raise AnalyzerError(f"模型拒絕了這個請求（{e.code}）", status_code=502) from e
    except errors.ServerError as e:
        raise AnalyzerError(f"模型端暫時不可用（{e.code}）", status_code=503) from e
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if not resp.text:
        raise AnalyzerError("模型回了空內容", status_code=502)

    u = resp.usage_metadata
    return AnalyzeResponse(
        model=resp.model_version or s.model,
        prompt=f"{tmpl.name}_{tmpl.version}",
        analysis=resp.text,
        usage=Usage(
            prompt_tokens=u.prompt_token_count or 0,
            thought_tokens=u.thoughts_token_count or 0,
            output_tokens=u.candidates_token_count or 0,
            total_tokens=u.total_token_count or 0,
        ),
        elapsed_ms=elapsed_ms,
    )
