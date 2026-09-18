"""模型呼叫的共用層。

把 client 建立、逾時、錯誤轉換、用量統計收在一個地方，
上面的 parser / matcher / rewriter / planner 只需要關心 prompt 和 schema。
"""

import json
import time
from dataclasses import dataclass
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LlmError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Usage:
    prompt_tokens: int = 0
    thought_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.thought_tokens + other.thought_tokens,
            self.output_tokens + other.output_tokens,
            self.total_tokens + other.total_tokens,
        )


@dataclass
class Result[TModel: BaseModel]:
    data: TModel
    usage: Usage
    elapsed_ms: int
    model: str


def _client() -> genai.Client:
    # client 存成區域變數再用。寫成 _client().models.xxx 的話暫時物件會被 GC
    # 回收並關掉底層 httpx 連線，在請求送出前就爆掉。
    s = get_settings()
    return genai.Client(
        vertexai=True,
        project=s.require_project_id(),
        location=s.location,
        http_options=types.HttpOptions(api_version="v1", timeout=120_000),
    )


def _usage_of(resp) -> Usage:
    u = resp.usage_metadata
    if u is None:
        return Usage()
    return Usage(
        prompt_tokens=u.prompt_token_count or 0,
        thought_tokens=u.thoughts_token_count or 0,
        output_tokens=u.candidates_token_count or 0,
        total_tokens=u.total_token_count or 0,
    )


def call_json(prompt: str, schema: type[T], *, thinking_budget: int | None = None) -> Result[T]:
    """要模型回傳符合 schema 的 JSON，並用 pydantic 驗證。

    模型宣稱輸出 JSON 不代表它真的合法，也不代表欄位都對。
    這裡驗證失敗就丟錯，不做「盡力解析」—— 靜默吞掉格式錯誤會讓下游拿到半殘的資料。
    """
    s = get_settings()
    cfg = types.GenerateContentConfig(
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        response_mime_type="application/json",
        response_schema=schema,
    )
    if thinking_budget is not None:
        cfg.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)

    client = _client()
    started = time.perf_counter()
    try:
        resp = client.models.generate_content(model=s.model, contents=prompt, config=cfg)
    except errors.ClientError as e:
        raise LlmError(f"模型拒絕了這個請求（{e.code}）", status_code=502) from e
    except errors.ServerError as e:
        raise LlmError(f"模型端暫時不可用（{e.code}）", status_code=503) from e
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if not resp.text:
        raise LlmError("模型回了空內容", status_code=502)
    try:
        data = schema.model_validate(json.loads(resp.text))
    except (json.JSONDecodeError, ValidationError) as e:
        raise LlmError(f"模型輸出不符合 schema：{e}", status_code=502) from e

    return Result(
        data=data,
        usage=_usage_of(resp),
        elapsed_ms=elapsed_ms,
        model=resp.model_version or s.model,
    )
