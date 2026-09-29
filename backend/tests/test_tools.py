"""Agent 工具的邊界測試（Day 15）。不打模型。"""

import warnings

from google.adk.tools import FunctionTool

from app.agent.tools import validate_learning_plan
from app.schemas.plan import LearningPlan, PlanItem

# Day 14 agent 實際送進來的東西，欄位名稱全部是它自己取的
DAY14_PLAN = {
    "total_duration_hours": 24,
    "weekly_hours_limit": 6,
    "weeks": [
        {"week_number": 1, "topic": "HTTP 基礎與進階", "duration_hours": 6,
         "resource_ids": [], "prerequisites": []},
    ],
}


def _declared_params() -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = FunctionTool(validate_learning_plan)._get_declaration()
    return str(d.parameters_json_schema)


def test_model_sees_the_plan_schema():
    """改成型別之後，模型拿到的宣告裡要看得到真正的欄位名稱。"""
    params = _declared_params()
    for name in ("items", "week", "hours", "prerequisites", "resource_ids"):
        assert name in params
    assert "plan_json" not in params


def test_day14_plan_is_rejected_with_the_wrong_field_names():
    """以前會變成「計畫裡一個項目都沒有」，現在要指出哪幾個欄位不認得。"""
    out = validate_learning_plan(DAY14_PLAN)
    assert not out["ok"]
    assert {v["kind"] for v in out["violations"]} == {"invalid_schema"}
    details = " ".join(v["detail"] for v in out["violations"])
    assert "weeks" in details
    assert "計畫裡一個項目都沒有" not in details


def test_raw_dict_with_correct_fields_is_validated():
    """ADK 轉換失敗會把原始 dict 傳進來，格式對的 dict 也要能驗。"""
    out = validate_learning_plan({
        "weekly_hours_budget": 6,
        "total_hours": 6,
        "items": [{"week": 1, "topic": "HTTP 狀態碼", "hours": 6}],
    })
    assert out == {"ok": True, "violations": []}


def test_model_instance_is_validated():
    plan = LearningPlan(
        weekly_hours_budget=6,
        total_hours=10,
        items=[PlanItem(week=1, topic="A", hours=10)],
    )
    kinds = {v["kind"] for v in validate_learning_plan(plan)["violations"]}
    assert "weekly_over_budget" in kinds
