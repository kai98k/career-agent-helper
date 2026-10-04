"""部署打包的內容（Day 19）。不連雲端。

上傳到 staging bucket 的東西，平台的 service agent 讀得到，
所以打包時只能有程式跟資源清單，不能夾帶 .env、session 資料庫或履歷。
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from deploy_agent import build_dir  # noqa: E402


def test_package_contains_app_and_bundled_resources():
    out = build_dir()
    try:
        assert (out / "app" / "agent" / "agent.py").exists()
        assert (out / "app" / "_bundled" / "resources.json").exists()
    finally:
        shutil.rmtree(out)


def test_package_has_no_secrets_or_user_data():
    out = build_dir()
    try:
        names = [p.name for p in out.rglob("*")]
        assert ".env" not in names
        assert not [n for n in names if n.endswith((".db", ".pyc", ".pdf"))]
        assert "__pycache__" not in names
        assert not (out / "app" / ".sessions").exists()
    finally:
        shutil.rmtree(out)


def test_app_parses_on_python_311():
    """adk deploy cloud_run 的 Dockerfile 寫死 python:3.11-slim（Day 20）。

    本機跟 Agent Runtime 都是 3.12，用了 3.12 才有的語法，測試全過，
    到 Cloud Run 才在載入 agent 時 SyntaxError。
    """
    import ast

    app = Path(__file__).resolve().parents[1] / "app"
    for p in app.rglob("*.py"):
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p), feature_version=(3, 11))
