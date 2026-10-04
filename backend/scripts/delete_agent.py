"""刪掉部署的 agent（Day 19）。

    cd backend
    .venv/Scripts/python.exe scripts/delete_agent.py

force=True 會連同底下的 sessions 一起刪。不加的話，有 session 就刪不掉。
staging bucket 裡的打包檔不會被刪，要自己清。
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import vertexai  # noqa: E402

from app.config import get_settings  # noqa: E402

name = os.environ.get("AGENT_ENGINE_NAME")
if not name:
    raise SystemExit("請在 .env 設定 AGENT_ENGINE_NAME")
location = os.environ.get("AGENT_RUNTIME_LOCATION", "asia-east1")
client = vertexai.Client(project=get_settings().require_project_id(), location=location)
client.agent_engines.delete(name=name, force=True)
print(f"已刪除：{name}")
