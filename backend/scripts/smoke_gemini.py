"""賽前確認用：五行 Gemini 呼叫，跑得通代表環境與權限都對了。

    cd backend && python scripts/smoke_gemini.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google import genai  # noqa: E402

from app.config import get_settings  # noqa: E402


def main() -> None:
    s = get_settings()
    client = genai.Client(vertexai=True, project=s.require_project_id(), location=s.location)
    resp = client.models.generate_content(
        model=s.model,
        contents="用一句話回答：你收到這則訊息了嗎？",
    )
    print(f"[{s.model} @ {s.location}] {resp.text}")


if __name__ == "__main__":
    main()
