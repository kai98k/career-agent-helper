# Note：30 天文章

開賽 2026-09-15，結束 2026-10-14，一天一篇。

每篇的 frontmatter 有 `status`，寫作時依序改成 `draft` → `writing` → `done` → `published`。

## 兩條貫穿規則

1. **文章產出不綁當天技術動作的成功**。卡住就寫排查過程 —— 簡章要求每天一篇 300 字以上且切題，沒要求你每天都成功。這是緩衝來源。
2. **所有履歷資料全部虛構**，不使用任何真實履歷，包含自己的。

## 賽前三件事

- [ ] 開 billing、設預算告警
- [ ] 環境四樣裝完並釘住版本，跑 `backend/scripts/smoke_gemini.py` 確認通
- [ ] 寫完 Day 01 與 Day 02（Day 30 可先寫骨架）

## 進度

### 第1章：從想法到第一個可操作版本

| Day | 日期 | 標題 | 狀態 |
| --- | --- | --- | --- |
| 01 | 09/15 | [不只幫你改履歷：定義 AI 職涯學習助理的目標與邊界](./day-01-scope-and-boundaries.md) | writing |
| 02 | 09/16 | [認識 Gemini Enterprise Agent Platform：模型、SDK、ADK 與 Runtime 各做什麼？](./day-02-agent-platform-overview.md) | draft |
| 03 | 09/17 | [從零到第一次呼叫：環境建置排查紀錄](./day-03-environment-setup.md) | draft |
| 04 | 09/18 | [把一次性腳本變成服務：FastAPI 端點與第一筆帳單](./day-04-fastapi-endpoint.md) | draft |
| 05 | 09/19 | [讓作品看得見：用單頁 HTML 接上分析端點](./day-05-web-ui.md) | draft |

### 第2章：讓履歷分析有依據

| Day | 日期 | 標題 | 狀態 |
| --- | --- | --- | --- |
| 06 | 09/20 | [先有測試案例，再談 AI 準不準：建立虛構履歷與職缺資料集](./day-06-test-dataset.md) | draft |
| 07 | 09/21 | [讓模型輸出可被程式使用：履歷與職缺的結構化解析](./day-07-structured-output.md) | draft |
| 08 | 09/22 | [從貼文字到上傳 PDF：解析履歷、處理失敗與確認內容](./day-08-pdf-upload.md) | draft |
| 09 | 09/23 | [沒寫到不等於不會：建立職缺要求與履歷證據對照](./day-09-evidence-matching.md) | draft |
| 10 | 09/24 | [改得更清楚，而不是編得更厲害：不捏造經歷的履歷改寫](./day-10-honest-rewrite.md) | draft |

### 第3章：從分析結果走向學習行動

| Day | 日期 | 標題 | 狀態 |
| --- | --- | --- | --- |
| 11 | 09/25 | [先問清楚再下結論：設計技能與經驗的澄清流程](./day-11-clarifying-questions.md) | draft |
| 12 | 09/26 | [別讓 AI 憑空排課：產生個人化學習計畫，並用程式檢查時數與先修條件](./day-12-learning-plan-validation.md) | draft |
| 13 | 09/27 | [把建議變成可操作的介面：證據卡片、改寫對照與學習路線](./day-13-result-ui.md) | draft |

### 第4章：讓 Agent 有狀態，也有界線

| Day | 日期 | 標題 | 狀態 |
| --- | --- | --- | --- |
| 14 | 09/28 | [什麼時候才需要 Agent？把固定流程接上 Google ADK](./day-14-adk-when-and-why.md) | draft |
| 15 | 09/29 | [工具不是越多越好：設計查詢資源與驗證計畫的 Tool](./day-15-typed-tools.md) | draft |
| 16 | 09/30 | [讓對話延續：用 Sessions 保存澄清答案與計畫修訂](./day-16-sessions.md) | draft |
| 17 | 10/01 | [這份履歷只屬於這次分析：使用者隔離、資料保留與刪除](./day-17-privacy-and-deletion.md) | draft |
| 18 | 10/02 | [當履歷寫著「忽略規則」：測試 Prompt Injection 與工具邊界](./day-18-prompt-injection.md) | draft |

### 第5章：部署到平台，觀察真實行為

| Day | 日期 | 標題 | 狀態 |
| --- | --- | --- | --- |
| 19 | 10/03 | [從本機走向雲端：部署 ADK Agent 到 Agent Runtime](./day-19-deploy-agent-runtime.md) | draft |
| 20 | 10/04 | [Agent Runtime、Cloud Run 還是自己包？部署路徑的取捨](./day-20-deployment-tradeoffs.md) | draft |
| 21 | 10/05 | [串起網頁與雲端 Agent：身分驗證、存取控制與結果呈現](./day-21-frontend-cloud-auth.md) | draft |
| 22 | 10/06 | [一次分析到底做了什麼？用 Trace 追蹤模型與工具呼叫](./day-22-cloud-trace.md) | draft |
| 23 | 10/07 | [不記錄整份履歷，也要排查問題：Logging 與 Monitoring 實作](./day-23-logging-monitoring.md) | draft |
| 24 | 10/08 | [模型逾時、429、工具失敗怎麼辦？讓流程能重試，也知道何時停止](./day-24-retry-and-timeout.md) | draft |

### 第6章：用實驗證明作品的價值

| Day | 日期 | 標題 | 狀態 |
| --- | --- | --- | --- |
| 25 | 10/09 | [怎樣才算好建議？建立履歷分析與學習計畫的評估規準](./day-25-eval-rubric.md) | draft |
| 26 | 10/10 | [把改動變成可以比較的東西：整理這 25 天的 prompt 與 schema 版本](./day-26-prompt-schema-versioning.md) | draft |
| 27 | 10/11 | [什麼時候能信自動評分，什麼時候必須人看？](./day-27-llm-as-judge.md) | draft |
| 28 | 10/12 | [只換姓名，建議就變了？檢查偏誤、穩定性與未知資訊處理](./day-28-bias-and-stability.md) | draft |
| 29 | 10/13 | [Agent 真的比較好嗎？比較直接呼叫與 Agent 的品質、延遲及成本](./day-29-agent-vs-direct.md) | draft |
| 30 | 10/14 | [從履歷到下一步：完整 Demo、重現指南、資源清理與實作回顧](./day-30-final-demo-and-retro.md) | draft |

## 全域範圍

**不做**：面試練習（文字與語音皆不做）、任何語音功能、雲端 PDF 解析服務、搜尋引擎或爬蟲、多使用者帳號系統、付費機制、React 前端、Terraform 或任何 IaC、模型微調。

**技術棧**：Python 3.12、google-genai、google-adk>=2.0、google-cloud-aiplatform[agent_engines,adk]>=1.112、FastAPI + 單頁 HTML、pypdf、Agent Runtime（asia-east1）、Cloud Trace / Logging / Monitoring。

