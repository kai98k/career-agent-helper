"""/analyze 的契約測試。這裡不打真的 API —— 驗的是輸入驗證與錯誤轉換。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalyzeResponse, Usage
from app.services.analyzer import AnalyzerError

client = TestClient(app)


def _fake_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        model="gemini-2.5-flash",
        prompt="analyze_v1",
        analysis="1. 量化成果\n2. 補充細節\n3. 加上摘要",
        usage=Usage(prompt_tokens=258, thought_tokens=1367, output_tokens=600, total_tokens=2225),
        elapsed_ms=13708,
    )


def test_analyze_ok(monkeypatch):
    monkeypatch.setattr("app.main.analyze", lambda r, j=None, p=None: _fake_response())
    r = client.post("/analyze", json={"resume_text": "林可薇 後端工程師 四年經驗 " * 3})
    assert r.status_code == 200
    assert r.json()["usage"]["thought_tokens"] == 1367


def test_resume_too_short_is_rejected_before_calling_model():
    """短輸入要在進到模型之前就擋掉，不然每次手滑都是一次付費呼叫。"""
    r = client.post("/analyze", json={"resume_text": "太短"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "status_code,expected", [(502, 502), (503, 503)]
)
def test_model_errors_become_http_errors(monkeypatch, status_code, expected):
    def boom(resume_text, job_text=None, prompt_key=None):
        raise AnalyzerError("模型壞了", status_code=status_code)

    monkeypatch.setattr("app.main.analyze", boom)
    r = client.post("/analyze", json={"resume_text": "林可薇 後端工程師 四年經驗 " * 3})
    assert r.status_code == expected
    assert r.json()["detail"] == "模型壞了"
