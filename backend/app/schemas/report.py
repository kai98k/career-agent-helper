"""一次完整分析的總報告。

把四個階段的產出收在一起，並且把「程式驗證沒過」的東西集中列出來。
這個 unverified 區塊是給前端用的 —— 使用者該一眼看到哪些結論不可信，
而不是要自己去每張卡片裡找。
"""

from pydantic import BaseModel, Field

from app.schemas.matching import MatchReport
from app.schemas.plan import ValidatedPlan
from app.schemas.resume import SCHEMA_VERSION, ParsedJob, ParsedResume
from app.schemas.rewrite import RewriteReport


class UsageSummary(BaseModel):
    prompt_tokens: int = 0
    thought_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0


class AnalysisReport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    path: str = Field(description="pipeline 或 agent，Day 29 要拿來比較")
    model: str
    resume: ParsedResume
    job: ParsedJob | None = None
    matching: MatchReport | None = None
    rewrite: RewriteReport | None = None
    plan: ValidatedPlan | None = None
    usage: UsageSummary = Field(default_factory=UsageSummary)
    elapsed_ms: int = 0

    @property
    def problems(self) -> list[str]:
        """所有沒通過程式驗證的東西，集中在一起。"""
        out: list[str] = []
        if self.matching:
            for m in self.matching.unverified:
                out.append(f"[證據] {m.requirement}：{m.verification_note or '引用無法驗證'}")
        if self.rewrite:
            for r in self.rewrite.rejected:
                out.append(f"[改寫] {r.original[:24]}…：{r.verification_note or '未通過驗證'}")
        if self.plan:
            for v in self.plan.violations:
                out.append(f"[計畫] {v.detail}")
        return out
