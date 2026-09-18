"""學習計畫：LLM 生成，程式驗證（Day 12）。

核心主張是「不能只信 LLM 輸出」。模型很擅長產出一份讀起來合理的課表，
但時數會加錯、先修順序會顛倒、某一週會排到二十小時。
這些都是算得出來的，所以用算的，不要再問模型一次 ——
再問一次只是拿到第二個同源的意見。
"""

from collections import defaultdict

from app.schemas.plan import (
    LearningPlan,
    ValidatedPlan,
    Violation,
    ViolationKind,
)
from app.services import resources
from app.services.llm import Result, call_json

_PROMPT = """根據下面的落差分析，排一份學習計畫。

使用者每週可投入 {budget} 小時，計畫長度 {weeks} 週。

規則：
1. 每一項的 rationale 必須指回落差分析裡的具體內容，說明為什麼需要學這個。
   不要寫「這是業界趨勢」這種跟這個人無關的理由。
2. prerequisites 填其他項目的 topic 名稱，要完全一致。沒有先修就留空。
3. resource_ids 只能填下面【可用資源】清單裡的 id。
   清單裡沒有適合的就留空，**不要自己編 id，也不要編課程名稱或網址**。
4. 每一週的時數加總不可以超過 {budget} 小時。
5. total_hours 填所有項目時數的加總。

【落差分析】
{gaps}

【可用資源】
{resource_list}"""


def validate(plan: LearningPlan) -> ValidatedPlan:
    """純程式驗證。不呼叫模型，也不該呼叫。"""
    v: list[Violation] = []

    if not plan.items:
        v.append(Violation(kind=ViolationKind.EMPTY_PLAN, detail="計畫裡一個項目都沒有"))
        return ValidatedPlan(plan=plan, violations=v)

    # 1) 宣稱的總時數 vs 實際加總
    actual = round(sum(i.hours for i in plan.items), 2)
    if abs(actual - plan.total_hours) > 0.01:
        v.append(
            Violation(
                kind=ViolationKind.TOTAL_MISMATCH,
                detail=f"宣稱總時數 {plan.total_hours}，實際加總 {actual}",
            )
        )

    # 2) 每週上限
    per_week: dict[int, float] = defaultdict(float)
    for i in plan.items:
        per_week[i.week] += i.hours
    for week, hours in sorted(per_week.items()):
        if hours > plan.weekly_hours_budget + 0.01:
            v.append(
                Violation(
                    kind=ViolationKind.WEEKLY_OVER_BUDGET,
                    week=week,
                    detail=f"第 {week} 週排了 {round(hours, 2)} 小時，"
                    f"超過每週上限 {plan.weekly_hours_budget}",
                )
            )

    # 3) 先修順序：先修項目必須出現在更早的週
    earliest: dict[str, int] = {}
    for i in plan.items:
        earliest[i.topic] = min(earliest.get(i.topic, i.week), i.week)
    for i in plan.items:
        for pre in i.prerequisites:
            if pre not in earliest:
                v.append(
                    Violation(
                        kind=ViolationKind.PREREQ_UNKNOWN,
                        week=i.week,
                        detail=f"「{i.topic}」的先修「{pre}」不在計畫中",
                    )
                )
            elif earliest[pre] >= i.week:
                v.append(
                    Violation(
                        kind=ViolationKind.PREREQ_ORDER,
                        week=i.week,
                        detail=f"「{i.topic}」排在第 {i.week} 週，"
                        f"但先修「{pre}」排在第 {earliest[pre]} 週",
                    )
                )

    # 4) 資源 id 必須真的存在
    known = resources.known_ids()
    for i in plan.items:
        for rid in i.resource_ids:
            if rid not in known:
                v.append(
                    Violation(
                        kind=ViolationKind.UNKNOWN_RESOURCE,
                        week=i.week,
                        detail=f"「{i.topic}」引用了不存在的資源 id：{rid}",
                    )
                )

    return ValidatedPlan(plan=plan, violations=v)


def generate(gaps: str, *, weekly_hours: float = 10.0, weeks: int = 8) -> Result[LearningPlan]:
    available = resources.verified_only()
    listing = (
        "\n".join(
            f"- {r.id}｜{r.title}｜主題：{', '.join(r.topics)}｜約 {r.hours} 小時"
            for r in available
        )
        or "（目前沒有已核實的資源，resource_ids 一律留空）"
    )
    result = call_json(
        _PROMPT.format(
            budget=weekly_hours, weeks=weeks, gaps=gaps.strip(), resource_list=listing
        ),
        LearningPlan,
    )
    result.data.weekly_hours_budget = weekly_hours
    return result


def generate_and_validate(
    gaps: str, *, weekly_hours: float = 10.0, weeks: int = 8
) -> tuple[ValidatedPlan, Result[LearningPlan]]:
    result = generate(gaps, weekly_hours=weekly_hours, weeks=weeks)
    return validate(result.data), result
