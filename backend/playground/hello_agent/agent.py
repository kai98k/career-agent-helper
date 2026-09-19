"""Day 05 用來看 ADK dev UI 長什麼樣的最小 agent。

只會聊天，沒有工具，跟 app/ 底下的分析流程完全無關。
adk web 會從這個資料夾往上找 .env，所以直接吃 backend/.env 的設定。
"""

import os

from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="hello_agent",
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    instruction="你是一個測試用的助理，用繁體中文簡短回答。",
)
