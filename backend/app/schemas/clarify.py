"""澄清問題與使用者的回答（Day 11）。

對照結果裡的 not_found 與 indirect 只代表「履歷沒寫」，不代表「不會」。
與其讓後面的計畫把它們當成缺口，不如先問使用者。
"""

from pydantic import BaseModel, Field

from app.schemas.resume import SCHEMA_VERSION, SchemaVersion


class ClarifyingQuestion(BaseModel):
    # --- 模型填 ---
    requirement: str = Field(description="這個問題對應的職缺要求，照抄候選清單裡的原文")
    question: str = Field(description="要問使用者的問題，要具體到能用一兩句話回答")
    why: str = Field(default="", description="為什麼要問，一句話")

    # --- 程式驗證後補上 ---
    grounded: bool | None = None  # requirement 是否真的在候選清單裡


class ClarifyReport(BaseModel):
    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION, validate_default=True)
    questions: list[ClarifyingQuestion] = Field(default_factory=list)


class Answer(BaseModel):
    requirement: str = Field(min_length=1, max_length=500)
    question: str = Field(default="", max_length=500)
    answer: str = Field(min_length=1, max_length=2_000)
