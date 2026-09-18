"""履歷改寫的結果（Day 10）。

同樣分成模型填的和程式驗證的兩半。
改寫是這個專案倫理立場最重的功能 —— 一個會幫你編數字的工具，
比一個什麼都不做的工具更危險，因為它產出的東西看起來就能直接用。
"""

from pydantic import BaseModel, Field

from app.schemas.resume import SCHEMA_VERSION


class RewriteItem(BaseModel):
    # --- 模型填 ---
    original: str = Field(description="履歷中的原句，一字不差")
    rewritten: str = Field(description="改寫後的句子")
    ask_user: str | None = Field(
        default=None,
        description="模型認為該補但原文沒有的資訊，寫成要問使用者的問題。不得自己填答案。",
    )

    # --- 程式驗證後補上 ---
    source_verified: bool | None = None
    invented_numbers: list[str] = Field(default_factory=list)
    invented_terms: list[str] = Field(default_factory=list)
    verification_note: str | None = None

    @property
    def safe(self) -> bool:
        return bool(self.source_verified) and not self.invented_numbers


class RewriteReport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    items: list[RewriteItem] = Field(default_factory=list)

    @property
    def rejected(self) -> list[RewriteItem]:
        return [i for i in self.items if not i.safe]
