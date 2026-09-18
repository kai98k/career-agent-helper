"""API 的輸入輸出契約。

Day 04 刻意只做到「純文字進、自由文字出」。回覆是一整段 Markdown，
程式沒辦法拿它做任何判斷 —— 這個限制留到結構化輸出那天解決。
"""

from pydantic import BaseModel, Field

from app import prompts


class AnalyzeRequest(BaseModel):
    resume_text: str = Field(
        min_length=20,
        max_length=20_000,
        description="履歷全文（純文字）。",
    )
    job_text: str | None = Field(
        default=None,
        max_length=20_000,
        description="職缺描述，選填。有給的話分析會對照著看。",
    )
    prompt: str = Field(
        default=prompts.DEFAULT,
        description="要用哪一版 prompt。可用："
        + "、".join(sorted(prompts.REGISTRY)),
    )


class Usage(BaseModel):
    """把 SDK 的 usage_metadata 攤平成自己的欄位，之後換模型或換 SDK 不用改呼叫端。"""

    prompt_tokens: int
    thought_tokens: int
    output_tokens: int
    total_tokens: int


class AnalyzeResponse(BaseModel):
    model: str
    prompt: str = Field(description="實際用的 prompt 名稱與版本，例如 analyze_v1")
    analysis: str
    usage: Usage
    elapsed_ms: int


class PdfExtractResponse(BaseModel):
    """抽取結果先回給使用者確認，確認過的文字才送去 /analyze。

    不直接串成一步，是因為 pypdf 對版面複雜的履歷常常把欄位順序打亂，
    使用者需要有機會看到、也有機會修正。
    """

    text: str
    page_count: int
    char_count: int
    empty_pages: list[int] = Field(default_factory=list)
    warning: str | None = None
