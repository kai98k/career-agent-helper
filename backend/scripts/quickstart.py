"""Agent Platform 官方快速入門範例。

與官方文件的兩點差異，都寫在下面的註解裡：

1. 多了 load_dotenv()。官方假設環境變數已經 export 在 shell 裡，本機開發放在 .env。
2. model 改讀設定，不寫死。官方範例寫的是 "gemini-3.5-flash"。

    cd backend
    .venv/Scripts/python.exe scripts/quickstart.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402

# --- 以下為官方範例（model 一行除外）---
from google import genai  # noqa: E402
from google.genai.types import HttpOptions  # noqa: E402

# get_settings() 內部會 load_dotenv()，所以 GOOGLE_CLOUD_PROJECT 等
# SDK 約定的變數在這行之後才進得到 os.environ，genai.Client() 才讀得到。
settings = get_settings()

client = genai.Client(http_options=HttpOptions(api_version="v1"))
response = client.models.generate_content(
    model=settings.model,  # 官方範例此處寫死 "gemini-3.5-flash"
    contents="AI怎麼運作的?",
)
print(response.text)
