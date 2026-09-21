"""職缺要求與履歷證據的對照結果。

分成兩半：模型填的，和程式驗證後補上的。
這個分界是刻意的 —— 模型可以說它引用了某句話，但那句話存不存在由程式決定。
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.resume import SCHEMA_VERSION, SchemaVersion


class MatchVerdict(str, Enum):
    DIRECT = "direct"        # 履歷有明確寫到
    INDIRECT = "indirect"    # 可從相關經歷推得，但沒有直說
    NOT_FOUND = "not_found"  # 履歷沒有相關內容


class RequirementMatch(BaseModel):
    # --- 以下由模型填 ---
    requirement: str
    verdict: MatchVerdict
    quote: str | None = Field(
        default=None, description="支持判定的履歷原句。NOT_FOUND 時必須留空。"
    )
    reasoning: str = Field(default="", description="一句話說明，不要複述引用內容")

    # --- 以下由程式驗證後補上，模型不得填寫 ---
    quote_verified: bool | None = None
    quote_start: int | None = None
    quote_end: int | None = None
    verification_note: str | None = None

    @property
    def trustworthy(self) -> bool:
        """判定為有證據時，那段引用必須通過驗證，否則這一條不可信。"""
        if self.verdict is MatchVerdict.NOT_FOUND:
            return True
        return bool(self.quote_verified)


class MatchReport(BaseModel):
    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION, validate_default=True)
    matches: list[RequirementMatch] = Field(default_factory=list)

    @property
    def unverified(self) -> list[RequirementMatch]:
        return [m for m in self.matches if not m.trustworthy]

    @property
    def counts(self) -> dict[str, int]:
        out = {v.value: 0 for v in MatchVerdict}
        for m in self.matches:
            out[m.verdict.value] += 1
        return out
