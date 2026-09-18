"""計畫驗證測試。全部不打模型 —— 這一層的重點就是不靠模型也能抓出問題。"""

from app.schemas.plan import LearningPlan, PlanItem, ViolationKind
from app.services.planner import validate


def _plan(items, budget=10.0, total=None):
    total = sum(i.hours for i in items) if total is None else total
    return LearningPlan(weekly_hours_budget=budget, total_hours=total, items=items)


def test_valid_plan_has_no_violations():
    p = _plan([
        PlanItem(week=1, topic="SQL 基礎", hours=6),
        PlanItem(week=2, topic="PostgreSQL 調校", hours=8, prerequisites=["SQL 基礎"]),
    ])
    assert validate(p).ok


def test_empty_plan():
    assert validate(_plan([])).violations[0].kind is ViolationKind.EMPTY_PLAN


def test_total_hours_mismatch_is_caught():
    p = _plan([PlanItem(week=1, topic="SQL", hours=6)], total=20)
    kinds = [v.kind for v in validate(p).violations]
    assert ViolationKind.TOTAL_MISMATCH in kinds


def test_weekly_budget_exceeded():
    p = _plan([
        PlanItem(week=1, topic="A", hours=7),
        PlanItem(week=1, topic="B", hours=6),
    ], budget=10)
    vs = [v for v in validate(p).violations if v.kind is ViolationKind.WEEKLY_OVER_BUDGET]
    assert len(vs) == 1
    assert vs[0].week == 1


def test_prerequisite_scheduled_after_its_dependent():
    p = _plan([
        PlanItem(week=1, topic="PostgreSQL 調校", hours=5, prerequisites=["SQL 基礎"]),
        PlanItem(week=3, topic="SQL 基礎", hours=5),
    ])
    vs = [v for v in validate(p).violations if v.kind is ViolationKind.PREREQ_ORDER]
    assert len(vs) == 1


def test_prerequisite_in_same_week_is_also_a_violation():
    """同一週不算先修完成，先修必須在更早的週。"""
    p = _plan([
        PlanItem(week=2, topic="SQL 基礎", hours=4),
        PlanItem(week=2, topic="PostgreSQL 調校", hours=4, prerequisites=["SQL 基礎"]),
    ])
    kinds = [v.kind for v in validate(p).violations]
    assert ViolationKind.PREREQ_ORDER in kinds


def test_unknown_prerequisite():
    p = _plan([PlanItem(week=1, topic="A", hours=3, prerequisites=["不存在的東西"])])
    kinds = [v.kind for v in validate(p).violations]
    assert ViolationKind.PREREQ_UNKNOWN in kinds


def test_hallucinated_resource_id_is_caught():
    """模型最愛編的就是課程 id 跟網址。"""
    p = _plan([PlanItem(week=1, topic="A", hours=3, resource_ids=["udemy-course-12345"])])
    vs = [v for v in validate(p).violations if v.kind is ViolationKind.UNKNOWN_RESOURCE]
    assert len(vs) == 1
    assert "udemy-course-12345" in vs[0].detail
