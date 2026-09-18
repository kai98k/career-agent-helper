---
day: 04
chapter: 1
chapter_title: 從想法到第一個可操作版本
title: 把一次性腳本變成服務：FastAPI 端點與第一筆帳單
date: 2026-09-18
status: writing
---

# Day 04｜把一次性腳本變成服務：FastAPI 端點與第一筆帳單

> Recap: 昨天跑出了第一次呼叫，但那還是一支「改一行、跑一次」的腳本

昨天那支腳本是能動，可是換個問法就要回去改 `contents=` 那一行
想比較兩種寫法哪個好，得跑兩次然後自己在終端機往上捲
跑完也沒地方留

今天把它變成一個端點

## 端點

```python
@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_resume(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return analyze(req.resume_text, req.job_text, req.prompt)
    except AnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
```

`main.py` 只做路由跟狀態碼轉換，呼叫模型的邏輯放在 `services/analyzer.py`

中間包一層自己的 `AnalyzerError`，讓路由層不用認識 SDK 的例外型別
等後面換了執行環境，要改的只有 analyzer

回應裡我多放了兩個欄位，`usage` 和 `elapsed_ms`
它們不是產品需求，是我要拿來算帳跟量延遲用的
第一版就放進去，比之後回頭加容易很多

## 第一筆帳單

包成端點之後，呼叫從「偶爾跑一次」變成「隨手就打」
成本這時候才從小數點後面的東西，變成要盯著看的東西

拿一份虛構履歷打一次

```json
{
  "elapsed_ms": 13708,
  "usage": {
    "prompt_tokens": 258,
    "thought_tokens": 1367,
    "output_tokens": 600,
    "total_tokens": 2225
  }
}
```

`thought_tokens` 是 1367，比實際輸出的 600 還多一倍以上，佔了總量 61%
而思考 token 是按輸出價計費的

Gemini 2.5 系列預設開啟思考，不設 `thinking_budget` 就是讓模型自己決定要想多久

```python
types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0)
)
```

關掉之後同一份履歷是 709 token、5.2 秒，差 3.1 倍
而兩份輸出講的是同三件事：量化成果、補充細節、加上摘要

但我不打算現在就無腦關掉它
這只是用一份履歷測出來的結論，而這種任務本來就不太需要推理
要當成結論得有對照組，那是後面的事

## 保險絲

Console 的預算設定有兩種，差別很大

- 僅傳送警告：寄信給你，服務照跑
- 強制執行支出上限：直接把服務停掉，要手動解除

我兩個都設了
上限 $10 防手滑，告警 50% 和 80% 讓我在被停掉之前先知道

<!-- 截圖：預算設定頁 -->

## 明天

把這個端點接上畫面
動手之前要先確認一件事：ADK 自帶的 dev UI 夠不夠用
夠的話，這篇就會變成「為什麼我不自己刻前端」!

---

<!-- 待補
- [ ] 截圖：/docs 的 Swagger 畫面
- [ ] 截圖：預算設定頁
- [ ] 實際去 Console 設「僅傳送警告」的預算（目前只有強制上限那一個）
-->

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
