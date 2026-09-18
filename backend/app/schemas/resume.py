"""履歷與職缺的結構化表示。

schema_version 不是裝飾。之後要比較「換了 prompt 之後結果有沒有變好」，
必須知道某一筆結果是哪一版 schema 產生的，否則跨版本的比較沒有意義。
改欄位就升版本，不要原地改意思。
"""

from enum import Enum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "v1"


class ExperienceItem(BaseModel):
    company: str
    title: str
    period: str | None = Field(default=None, description="原文怎麼寫就怎麼填，不要正規化")
    bullets: list[str] = Field(default_factory=list, description="逐條直接取自原文")


class ParsedResume(BaseModel):
    schema_version: str = SCHEMA_VERSION
    name: str | None = None
    headline: str | None = None
    years_experience: float | None = Field(
        default=None, description="履歷明講才填，推算出來的一律留空"
    )
    experiences: list[ExperienceItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(
        default_factory=list,
        description="履歷完全沒提到的欄位名稱。空著跟沒寫是兩回事，要能分辨。",
    )


class RequirementKind(str, Enum):
    MUST = "must"
    NICE = "nice"


class Requirement(BaseModel):
    text: str = Field(description="逐條取自職缺原文，不要合併也不要改寫")
    kind: RequirementKind = RequirementKind.MUST


class ParsedJob(BaseModel):
    schema_version: str = SCHEMA_VERSION
    title: str
    company: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)
