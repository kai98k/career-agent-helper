"""用 adk deploy cloud_run 部署同一個 agent（Day 20，拿來跟 Agent Runtime 比較）。

    cd backend
    .venv/Scripts/python.exe scripts/deploy_cloud_run.py

跟 Agent Runtime 不一樣的地方，都寫在這支腳本裡：

- adk deploy cloud_run 只複製「agent 那個資料夾」，不支援 extra_packages
  （ADK 2.8.0 的 cli_deploy.py 裡寫死 extra_packages_copy=''）。
  我們的 agent 會 import app.services...，所以要包一個資料夾，把 app/ 放進去。
- 產生的 Dockerfile 把 GOOGLE_CLOUD_LOCATION 設成部署區域，
  gemini-2.5-flash 在 asia-east1 會 404（Day 19），所以要用 --set-env-vars 蓋掉。
- session 預設是 memory://，instance 一縮到 0 就全部不見。
  這裡接 Day 19 的 Agent Runtime Sessions，兩條路共用同一個 session 存放處。

**這會建立會計費的雲端資源。** 測完跑：
    gcloud run services delete career-agent-helper --region asia-east1
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from deploy_agent import REQUIREMENTS, build_dir  # noqa: E402

from app.config import get_settings  # noqa: E402

APP_NAME = "career_advisor"
SERVICE = "career-agent-helper"

# ADK 的 Dockerfile 會自己 pip install google-adk，這裡只放其他的。
# google-cloud-aiplatform 不能省：session 接 agentengine:// 要用到 vertexai 模組，
# 但 ADK 產生的 Dockerfile 只裝 google-adk[a2a]，少了它容器一啟動就
# ModuleNotFoundError: No module named 'vertexai'（Day 20 實測）。
_EXTRA = [r for r in REQUIREMENTS if not r.startswith(("google-adk", "cloudpickle"))]

_WRAPPER = '''"""Cloud Run 用的包裝（Day 20）。

adk api_server 只認 agents/<名稱>/ 底下的 agent.py，
而我們的程式是 app/ 這個套件，所以把 app/ 放在同一個資料夾，再把資料夾加進 sys.path。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agent.agent import root_agent  # noqa: E402,F401
'''


def build_agent_folder() -> Path:
    src = build_dir()  # 跟 Agent Runtime 用同一份：app/ + _bundled/resources.json
    folder = Path(tempfile.mkdtemp(prefix="cloudrun-src-")) / APP_NAME
    folder.mkdir()
    shutil.move(str(src / "app"), folder / "app")
    shutil.rmtree(src)
    (folder / "__init__.py").write_text("from . import agent  # noqa: F401\n", encoding="utf-8")
    (folder / "agent.py").write_text(_WRAPPER, encoding="utf-8")
    (folder / "requirements.txt").write_text("\n".join(_EXTRA) + "\n", encoding="utf-8")
    return folder


def main() -> None:
    s = get_settings()
    project = s.require_project_id()
    region = os.environ.get("AGENT_RUNTIME_LOCATION", "asia-east1")
    engine = os.environ.get("AGENT_ENGINE_NAME")
    if not engine:
        raise SystemExit("需要 .env 的 AGENT_ENGINE_NAME：session 接 Day 19 的 Agent Runtime Sessions")

    folder = build_agent_folder()
    print(f"agent 資料夾：{folder}")
    adk = BACKEND / ".venv" / "Scripts" / "adk.exe"
    cmd = [
        str(adk), "deploy", "cloud_run",
        "--project", project,
        "--region", region,
        "--service_name", SERVICE,
        "--app_name", APP_NAME,
        "--session_service_uri", f"agentengine://{engine}",
        str(folder),
        "--",
        # 不開放未驗證的存取：api_server 的網址裡就有 user_id，打得到就讀得到所有人的 session
        "--no-allow-unauthenticated",
        "--min-instances=0",
        "--max-instances=1",
        f"--set-env-vars=GOOGLE_CLOUD_LOCATION={s.location},GEMINI_MODEL={s.model}",
        # 不指定的話用 Compute Engine 預設的 service account。
        # 換成專屬帳號，只給 roles/aiplatform.user（呼叫 Gemini、讀寫 Agent Runtime 的 session）
        f"--service-account=career-agent-run@{project}.iam.gserviceaccount.com",
        "--quiet",
    ]
    subprocess.run(cmd, check=True)

    # adk deploy 失敗時會印 "Deploy failed"，但 exit code 還是 0（Day 20 實測）。
    # 不能信 exit code，直接去問 Cloud Run 這個服務有沒有起來。
    gcloud = "gcloud.cmd" if os.name == "nt" else "gcloud"
    url = subprocess.run(
        [gcloud, "run", "services", "describe", SERVICE, "--region", region,
         "--project", project, "--format=value(status.url)"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not url:
        raise SystemExit("Cloud Run 上找不到這個服務，部署其實失敗了，往上看 adk 的輸出")
    print(f"\n服務網址：{url}")


if __name__ == "__main__":
    main()
