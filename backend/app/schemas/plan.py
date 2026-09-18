"""學習計畫與它的驗證結果（Day 12）。

LLM 生成計畫，程式檢查計畫。這兩件事分開是這一層的重點：
時數會不會加錯、先修順序有沒有顛倒、每週會不會排爆，
這些都是算得出來的，不需要也不應該再問一次模型。
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.resume import SCHEMA_VERSION


class PlanItem(BaseModel):
    week: int = Field(ge=1, description="第幾週，從 1 開始")
    topic: str
    hours: float = Field(gt=0, description="這一項預估要花的時數")
    prerequisites: list[str] = Field(
        default_factory=list, description="必須先完成的 topic 名稱，要跟其他項目的 topic 完全一致"
    )
    resource_ids: list[str] = Field(
        default_factory=list, description="只能引用資源清單裡實際存在的 id"
    )
    rationale: str = Field(default="", description="為什麼需要學這個，要能對回履歷或職缺")


class LearningPlan(BaseModel):
    schema_version: str = SCHEMA_VERSION
    weekly_hours_budget: float = Field(default=10.0, description="使用者每週可投入的時數")
    total_hours: float = Field(default=0.0, description="模型自己宣稱的總時數")
    items: list[PlanItem] = Field(default_factory=list)


class ViolationKind(str, Enum):
    TOTAL_MISMATCH = "total_mismatch"
    WEEKLY_OVER_BUDGET = "weekly_over_budget"
    PREREQ_ORDER = "prereq_order"
    PREREQ_UNKNOWN = "prereq_unknown"
    UNKNOWN_RESOURCE = "unknown_resource"
    EMPTY_PLAN = "empty_plan"


class Violation(BaseModel):
    kind: ViolationKind
    detail: str
    week: int | None = None


class ValidatedPlan(BaseModel):
    plan: LearningPlan
    violations: list[Violation] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations
