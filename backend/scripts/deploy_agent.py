"""把 agent 部署到 Agent Runtime（Day 19）。

    cd backend
    .venv/Scripts/python.exe scripts/deploy_agent.py

需要的環境變數（放 .env）：
    GOOGLE_CLOUD_PROJECT     專案
    AGENT_RUNTIME_LOCATION   部署區域，預設 asia-east1
    STAGING_BUCKET           gs://...，SDK 會把打包好的程式放這裡，要跟部署區域同一區

已經部署過、要更新程式或設定：加上 --update（需要 .env 的 AGENT_ENGINE_NAME）

部署的東西只有 app/ 這個資料夾，加上一份資源清單。
FastAPI、runner.py、SQLite 都不會上去：雲端跑 agent 的是平台的 AdkApp。

**這會建立一個會計費的雲端資源。** 測完記得跑 scripts/delete_agent.py。
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

import vertexai  # noqa: E402
from vertexai.agent_engines import AdkApp  # noqa: E402

from app.agent.agent import build_agent  # noqa: E402
from app.config import get_settings  # noqa: E402

# 只放 agent 實際 import 得到的套件，版本跟本機 lock 檔一致。
# 雲端用的是 pickle 過的 agent，本機跟雲端的套件版本不一樣，反序列化就可能炸。
REQUIREMENTS = [
    "google-adk==2.8.0",
    "google-genai==2.22.0",
    "google-cloud-aiplatform[agent_engines,adk]==2.1.0",
    "cloudpickle==3.1.2",
    "pydantic==2.13.5",
    "python-dotenv==1.2.3",
]


def build_dir() -> Path:
    """把要上傳的東西整理到一個暫存資料夾。

    SDK 用 tar.add(路徑) 打包，路徑原樣變成壓縮檔裡的路徑，
    所以要在一個乾淨的資料夾裡、用相對路徑 "app" 打包。
    """
    out = Path(tempfile.mkdtemp(prefix="agent-build-"))
    shutil.copytree(
        BACKEND / "app",
        out / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_bundled"),
    )
    bundled = out / "app" / "_bundled"
    bundled.mkdir()
    shutil.copy(ROOT / "data" / "resources" / "resources.json", bundled / "resources.json")
    return out


def main() -> None:
    s = get_settings()
    project = s.require_project_id()
    location = os.environ.get("AGENT_RUNTIME_LOCATION", "asia-east1")
    bucket = os.environ.get("STAGING_BUCKET", "")
    if not bucket.startswith("gs://"):
        raise SystemExit("請在 .env 設定 STAGING_BUCKET=gs://...")

    client = vertexai.Client(project=project, location=location)
    app = AdkApp(agent=build_agent())

    src = build_dir()
    os.chdir(src)  # extra_packages 用相對路徑，壓縮檔裡才會是 app/...
    print(f"打包目錄：{src}")

    config = {
        "display_name": "career-agent-helper",
        "description": "履歷與職缺落差分析（30 天鐵人賽作品）",
        "requirements": REQUIREMENTS,
        "extra_packages": ["app"],
        "staging_bucket": bucket,
        # 預設 min_instances=1：沒有人用也一直開著一台在計費。
        # 這是 demo，冷啟動慢一點可以接受。
        "min_instances": 0,
        "max_instances": 1,
        "env_vars": {
            "GEMINI_MODEL": s.model,
            # Agent Runtime 在 asia-east1，但 gemini-2.5-flash 在 asia-east1 回 404（Day 19 實測）。
            # AdkApp.set_up() 會把 GOOGLE_CLOUD_LOCATION 設成部署區域，除非這裡先給了值，
            # 所以要明講模型走哪裡。跟本機 .env 用同一個值，兩邊才一致。
            "GOOGLE_CLOUD_LOCATION": s.location,
        },
    }

    if "--update" in sys.argv:
        name = os.environ.get("AGENT_ENGINE_NAME")
        if not name:
            raise SystemExit("--update 需要 .env 的 AGENT_ENGINE_NAME")
        remote = client.agent_engines.update(name=name, agent=app, config=config)
        print(f"\n更新完成：{remote.api_resource.name}")
        return

    remote = client.agent_engines.create(agent=app, config=config)
    print(f"\n部署完成：{remote.api_resource.name}")
    print("把它放進 .env：AGENT_ENGINE_NAME=" + remote.api_resource.name)


if __name__ == "__main__":
    main()
