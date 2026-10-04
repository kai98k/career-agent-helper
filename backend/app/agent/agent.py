"""職涯分析 agent（路徑 B，Day 14-16）。

什麼時候才需要 agent？固定流程（services/pipeline.py）已經能做完整套分析，
而且順序寫死、成本可預測。agent 值得存在的理由只有一個：
**它可以決定要不要多做一步**。

具體來說：履歷資訊不足時先問清楚再分析，而不是硬著頭皮猜；
驗證沒過時自己退回去改，而不是把有問題的結果交出去。
固定流程做不到這兩件事，因為它沒有分支。

這個假設對不對要用資料回答 —— Day 29 會拿同一批測試資料，
比這條路和固定流程的品質、延遲與成本。在那之前它只是假設。
"""

from google.adk.agents import LlmAgent

from app.agent.callbacks import guard_reply, limit_llm_calls
from app.agent.instruction import INSTRUCTION, REPORT_NOTICE  # noqa: F401（給測試與 eval 用）
from app.agent.tools import lookup_resources, validate_learning_plan, verify_evidence
from app.config import get_settings

def build_agent(*, use_guard: bool = True, model=None) -> LlmAgent:
    """呼叫次數上限跟回覆檢查都掛在 agent 上，不放在 runner（Day 19）。

    部署到 Agent Runtime 之後，跑 agent 的是平台的 AdkApp，不是 runner.py。
    放在 runner 的東西，上雲端就不見了。

    use_guard=False 只給 eval 用：要看模型「本來」寫了什麼。
    model 只給測試用：換成假的模型，不打 API 也能測 callback。
    """
    s = get_settings()
    return LlmAgent(
        name="career_advisor",
        model=model or s.model,
        description="分析履歷與職缺的落差，並產出有依據的建議與學習計畫。",
        instruction=INSTRUCTION,
        tools=[verify_evidence, lookup_resources, validate_learning_plan],
        before_model_callback=limit_llm_calls,
        after_model_callback=guard_reply if use_guard else None,
    )


# ADK 的 dev UI 與 adk deploy 會找模組層級的 root_agent
root_agent = build_agent()
