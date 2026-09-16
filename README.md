# Career Agent Helper

AI 職涯學習助理：讀一份履歷與一則職缺，做出**有證據可追溯**的落差分析、**不捏造經歷**的改寫建議，以及**經程式驗證過時數與先修順序**的學習計畫。

這個 repo 同時是一場 30 天鐵人賽的實作紀錄，主軸是「把 demo 級 AI 應用推到可上線標準」—— 評估、隱私、可觀測性、失敗處理都算在內。文章在 [Note/](./Note/)。

## 這個專案要解決什麼

- 履歷分析常見的問題是**講得漂亮但沒有依據**。這裡每一條結論都要指回履歷原文片段。
- 改寫建議常見的問題是**幫你編經歷**。這裡的硬約束是只能重組與強化既有事實。
- 學習計畫常見的問題是**LLM 憑空排課**。這裡的時數加總、先修順序、每週上限由程式驗證，不只信模型輸出。

## 明確不做

面試練習（文字與語音皆不做）、任何語音功能、雲端 PDF 解析服務、搜尋引擎或爬蟲、多使用者帳號系統、付費機制、React 前端、Terraform 或任何 IaC、模型微調。

## 技術棧

Python 3.12、google-genai、google-adk>=2.0、google-cloud-aiplatform[agent_engines,adk]>=1.112、
FastAPI + 單頁 HTML、pypdf、Agent Runtime（asia-east1）、Cloud Trace / Logging / Monitoring。

## 目錄

```
Note/            30 天文章（README.md 是索引）
backend/
  app/           FastAPI 應用（config、main、schemas）
  prompts/       各版本 prompt（Day 26 會整理成有標記的版本）
  scripts/       smoke_gemini.py 等一次性腳本
  tests/
data/
  resumes/       虛構履歷（Day 06）
  jobs/          職缺描述（Day 06）
  resources/     人工核實過的學習資源 JSON（Day 13）
evals/           評估規準、批次執行與報表（Day 25–29）
```

## 開始

```bash
py -3.12 -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.lock.txt   # 釘死的版本；新增套件時改 requirements.txt 再重新 freeze

cp .env.example .env            # 填入 GOOGLE_CLOUD_PROJECT
gcloud auth application-default login

python backend/scripts/smoke_gemini.py   # 五行呼叫，確認環境通了
cd backend && uvicorn app.main:app --reload
```

`GET /healthz` 會回報目前的 region、模型與 project 是否已設定。

## 資料原則

**所有履歷資料全部虛構**，不使用任何真實履歷，包含作者自己的。日誌不記錄履歷全文，可進日誌的欄位在 Day 23 收口。
