"""集中管理環境設定，避免各處散落 os.environ。"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    project_id: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location: str = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-east1")
    use_vertexai: bool = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "True") == "True"
    model: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    app_env: str = os.environ.get("APP_ENV", "local")
    max_upload_mb: int = int(os.environ.get("MAX_UPLOAD_MB", "5"))
    max_pdf_pages: int = int(os.environ.get("MAX_PDF_PAGES", "10"))

    def require_project_id(self) -> str:
        if not self.project_id:
            raise RuntimeError("缺少 GOOGLE_CLOUD_PROJECT，請先複製 .env.example 成 .env")
        return self.project_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
