"""Agent 的工具（Day 15）。

三個工具，全部是**確定性的程式邏輯**，沒有一個會再去問模型。
這是刻意的：agent 這一層的價值如果是「多問模型幾次」，那它不值得存在。
它的價值在於能自己決定何時去做那些模型做不到的事 —— 查一份人工核實過的清單、
把一段引用拿去原文裡比對、把一份課表拿去算時數。

工具都包既有的 services，不重寫一份。Day 29 要比較固定流程與 agent，
如果兩邊的驗證邏輯是兩份程式碼，比出來的就不是 agent 的價值。
"""

import json

from google.adk.tools import ToolContext

from app.schemas.plan import LearningPlan
from app.services import evidence, planner, resources

# 履歷放在 session state 裡，工具透過 ToolContext 取用。
#
# 理由不是省 token（履歷本來就會經由 instruction 的 {resume_text} 模板
# 每輪送出去），而是**驗證的對象必須是原始文字**。
# 如果讓 agent 把履歷當參數傳進工具，它傳的是它「記得的版本」，
# 那就變成拿模型的記憶去驗證模型的引用，兩邊同源，驗了等於沒驗。
STATE_RESUME = "resume_text"


def verify_evidence(quotes: list[str], tool_context: ToolContext) -> dict:
    """確認這些引用真的出現在使用者的履歷裡。

    在你宣稱履歷「有寫到」某件事之前，必須用這個工具驗證你要引用的原句。
    回傳 exact 表示可以引用；altered 表示你改過字，必須改回原文；
    not_found 表示履歷裡沒有這句話，你不可以宣稱它存在。

    Args:
        quotes: 你打算引用的履歷原句清單。

    Returns:
        每一句的驗證結果，以及一份不可使用的清單。
    """
    resume = tool_context.state.get(STATE_RESUME)
    if not resume:
        return {"error": "session 裡沒有履歷，無法驗證。請先請使用者提供履歷。"}

    checks = evidence.verify_all(quotes, resume)
    return {
        "results": [
            {
                "quote": c.quote,
                "verdict": c.verdict.value,
                "similarity": round(c.similarity, 3),
                "closest_text_in_resume": c.closest,
            }
            for c in checks
        ],
        "unusable": [c.quote for c in checks if not c.ok],
    }


def lookup_resources(topics: list[str]) -> dict:
    """依主題查詢學習資源。

    只會回傳人工核實過的資源。查不到就是查不到，
    **不要自己編課程名稱、id 或網址** —— 編出來的連結打不開，
    對一個正在找工作的人來說那比沒有建議更糟。

    Args:
        topics: 主題關鍵字，例如 ["kubernetes", "docker"]。

    Returns:
        符合的資源清單，可能是空的。
    """
    found = resources.search(topics)
    return {
        "resources": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "kind": r.kind,
                "hours": r.hours,
                "topics": r.topics,
            }
            for r in found
        ],
        "note": (
            "查無已核實的資源，請把 resource_ids 留空"
            if not found
            else f"找到 {len(found)} 筆，只能引用這些 id"
        ),
    }


def validate_learning_plan(plan_json: str) -> dict:
    """檢查一份學習計畫有沒有違反硬性限制。

    檢查項目：總時數加總是否正確、每週是否超過使用者可投入的時數、
    先修項目是否排在更早的週、引用的資源 id 是否真的存在。

    產出計畫之後**必須**用這個工具檢查過才能交給使用者。
    如果有 violations，請修正計畫並重新檢查，不要把有問題的計畫交出去。

    Args:
        plan_json: 符合 LearningPlan schema 的 JSON 字串。

    Returns:
        ok 與 violations 清單。
    """
    try:
        plan = LearningPlan.model_validate(json.loads(plan_json))
    except Exception as e:
        return {"ok": False, "violations": [{"kind": "invalid_json", "detail": str(e)}]}

    result = planner.validate(plan)
    return {
        "ok": result.ok,
        "violations": [
            {"kind": v.kind.value, "week": v.week, "detail": v.detail}
            for v in result.violations
        ],
    }
