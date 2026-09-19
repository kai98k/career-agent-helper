---
day: 05
chapter: 1
chapter_title: 從想法到第一個可操作版本
title: 讓作品看得見：用單頁 HTML 接上分析端點
date: 2026-09-19
status: writing
---

# Day 05｜讓作品看得見：用單頁 HTML 接上分析端點

> Recap: 昨天把腳本包成 `/analyze`，可是要用它還得開 Swagger、手動貼 JSON

Swagger 給我自己用夠了
但要拿給別人看，叫對方打開 `/docs`、把履歷的換行一個一個跳脫成 `\n`，這不叫作品

今天要讓它有一個畫面

## 為什麼第五天就碰到 ADK

要做畫面，最省事的方法是找一個現成的
我的技術棧裡，唯一自帶畫面的就是 ADK

`adk web` 一行指令就會開出一個網頁，可以直接跟 agent 對話
如果它夠用，前端這件事今天就結束了

所以昨天說，動手刻之前先看它一眼
但要看懂那個畫面，得先知道 ADK 本身在做什麼

## ADK 是什麼

Day 02 把平台拆成四層：模型、Gen AI SDK、ADK、Agent Runtime
ADK（Agent Development Kit，套件名 `google-adk`）是第三層，負責「把模型組裝成 agent」

### 它幫你省掉什麼

Day 04 用的是 Gen AI SDK：送一段 prompt，拿回一段文字，一來一回就結束

```python
resp = client.models.generate_content(model=s.model, contents=prompt)
```

這對「分析一份履歷」夠用
但如果想讓模型：

- 自己決定要不要查資料、要查什麼
- 查完看結果，再決定下一步
- 記得使用者前一輪回答過什麼

這些用 SDK 都做得到，只是要自己寫
呼叫工具的迴圈、每一輪的對話紀錄、什麼時候該停，全都得自己管

ADK 就是把這些包好的框架

### 四個核心元件

| 元件 | 做什麼 | 對應的類別 |
| --- | --- | --- |
| Agent | 定義 agent：用哪個模型、指令是什麼、有哪些工具 | `LlmAgent`（別名 `Agent`），組合用的 `SequentialAgent`、`ParallelAgent`、`LoopAgent` |
| Tool | agent 能呼叫的能力，一般的 Python 函式就能直接當工具 | 函式本身，或包成 `FunctionTool` |
| Runner | 實際跑 agent loop 的引擎：送請求、執行工具、把結果送回模型，直到結束 | `Runner`、`InMemoryRunner` |
| Session | 保存一段對話的歷程與狀態 | `InMemorySessionService`、`DatabaseSessionService`、`VertexAiSessionService` |

寫 ADK 的時候，大部分時間只會碰到前兩個
Runner 跟 Session 在本機開發時，`adk` 指令會幫你準備好

Session 的三種實作剛好是三個階段：放記憶體（重開就沒了）、放本機資料庫、放雲端託管
Day 16 會從本機一路走到雲端

### 一個套件，附一整套指令

裝 `google-adk` 的時候，會順便裝一個 `adk` 指令：

| 指令 | 做什麼 |
| --- | --- |
| `adk create` | 建一個新的 agent 專案骨架 |
| `adk run` | 在終端機裡跟 agent 對話 |
| `adk web` | 開一個網頁版 dev UI 跟 agent 對話 ← 今天要看的 |
| `adk api_server` | 只開 API，不開畫面 |
| `adk eval` | 拿評估資料集跑 agent |
| `adk deploy` | 部署到 `agent_engine`、`cloud_run` 或 `gke` |

注意到了嗎？`adk deploy` 的子指令還叫 `agent_engine`
Day 02 講過 Agent Engine 已經改名成 Agent Runtime，但 2.8.0 的 CLI 還沒跟上
改的是名字不是服務本體，這又是一個例子

從本機開發、評估到部署，同一套工具走完
這也是它吸引人的地方：畫面是免費附的

## 先寫一個最小的 agent

`adk web` 不能直接開，它要一個 agent 才有東西可以顯示
我現在手上沒有 agent，只有 Day 04 那支 `analyze()`

所以先寫一個只會聊天的最小 agent，純粹拿來看畫面
放在 `backend/playground/`，跟正式的程式分開：

```
backend/playground/
└── hello_agent/
    ├── __init__.py
    └── agent.py
```

`__init__.py` 只有一行，讓 ADK 找得到 agent：

```python
from . import agent
```

`agent.py`：

```python
import os

from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="hello_agent",
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    instruction="你是一個測試用的助理，用繁體中文簡短回答。",
)
```

只設了三個欄位：名字、模型、指令
沒有工具、沒有子 agent，這是最陽春的 agent

ADK 認的是 `root_agent` 這個變數名，取別的名字它會說找不到 agent

環境變數不用另外設
`adk web` 會從 agent 的資料夾一路往上找 `.env`，所以直接讀到 Day 03 建好的 `backend/.env`

## 跑起來看

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
adk web playground
```

venv 沒啟動的話，PowerShell 會說找不到 `adk` 這個指令
`adk` 是跟著 google-adk 裝進 `.venv` 裡的，不是系統上的全域指令

打開 http://127.0.0.1:8000 會被轉到 `/dev-ui/`，左上角選 `hello_agent`

<!-- TODO 截圖：dev UI 畫面 -->

<!-- TODO 用自己的話寫：第一眼看到這個畫面的感想 -->

## 看完：為什麼不拿它當前端

看完我決定自己刻，理由有三個，而且都不是品味問題

### 一、它接不上我現在的東西

剛剛那個 `hello_agent` 只會聊天，跟履歷分析一點關係都沒有
要讓 dev UI 顯示真正的分析，我得把 Day 04 的 `analyze()` 整個改寫成 agent

Day 02 說過「不用 ADK 也能呼叫 Gemini」，Day 04 走的就是這條路
反過來，ADK 的畫面也就用不到我的程式

為了用它的畫面，我得先把架構改成 agent
可是「到底需不需要 agent」是 Day 14 才要回答的問題
不能因為想要一個畫面，就先把答案定了

### 二、官方自己說不要拿它上線

`adk web --help`：

> This server is intended for local development. Its endpoints are unauthenticated, so run it on a trusted network only and do not expose it to untrusted or public networks.

`adk deploy cloud_run --help` 裡的 `--with_ui`：

> WARNING: The web UI is for development and testing only — do not use in production.

這個系列的主軸是把 demo 推到可上線
第五天就選一個官方標明「不要上線」的介面，等於先欠一筆債

### 三、它是給開發者看 agent 在想什麼的

翻一下 dev UI 背後的 API 就知道它是做給誰的
除了對話用的 `/run`，其他路由幾乎都掛在 `/dev/` 底下：

- `debug/trace`：每一步呼叫的追蹤紀錄
- `eval_sets`、`run_eval`：建評估資料集、跑評估
- `graph`：把 agent 的結構畫成圖

這些在除錯 agent 的時候很好用，Day 14 之後我應該會常開它

但我的使用者要的是：貼一份履歷，拿回一份報告
他不需要看到 function call 的 JSON

### 一個沒預期的發現

跑完之後，`playground/hello_agent/` 底下多了一個 `.adk/session.db`

那是 dev UI 自己建的本機 SQLite，存著每一次對話
如果我在裡面貼過履歷，履歷就躺在原始碼資料夾裡，下次 `git add .` 就一起送上 GitHub

`.gitignore` 補上一行：

```gitignore
# adk web 會在 agent 目錄底下自建本機 session 資料庫，裡面可能有貼過的履歷
.adk/
```

這件事 Day 17 講資料保留時會再回來

結論是兩個都要
dev UI 留著當 agent 的除錯工具，給使用者的畫面自己做

ADK 今天只是借來看一眼
什麼時候真的需要 agent，等 Day 14 拿前面十幾天的經驗來回答

## 不用框架

一個 `web/index.html`，HTML、CSS、JS 全寫在一起，沒有 build step
FastAPI 直接把它當靜態檔掛出去：

```python
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
```

這段一定要放在 `main.py` 最後面
mount 在 `/` 會接走所有路徑，放在前面的話，`/analyze` 會先被靜態檔案那層接走，根本到不了我的路由

前後端同一個 origin 還有個附帶好處：不用處理 CORS

## 三個狀態

畫面本身很單純，左邊輸入、右邊結果
真正花時間的是「等待中」跟「失敗了」

### 等待中

昨天量到一次分析要 13 秒
13 秒畫面沒反應，使用者一定會再按一次，然後我付兩次錢

```javascript
function syncAnalyzeBtn() {
  // 分析途中一律鎖住按鈕，避免重複送出。
  var ready = !busy && resumeText.value.trim().length >= 20 && !!promptSel.value;
  analyzeBtn.disabled = !ready;
}
```

旁邊再加一個秒數計時
轉圈圈只說「還在跑」，秒數會說「跑多久了」
等了 30 秒跟等了 3 分鐘，使用者該做的決定不一樣

### 失敗了

FastAPI 的錯誤有兩種形狀

- 我自己丟的 `HTTPException`：`detail` 是字串
- pydantic 驗證失敗的 422：`detail` 是陣列

```json
{"detail": [{"type": "string_too_short", "loc": ["body", "resume_text"],
             "msg": "String should have at least 20 characters"}]}
```

前端如果只寫 `alert(err.detail)`，碰到第二種，使用者會看到 `[object Object]`

```javascript
function describeError(status, payload) {
  if (payload && typeof payload.detail === "string") {
    return { title: "錯誤 " + status, body: payload.detail };
  }
  if (payload && Array.isArray(payload.detail)) {
    return {
      title: "錯誤 " + status + "：輸入不符合規格",
      body: payload.detail.map(function (d) {
        var where = Array.isArray(d.loc) ? d.loc.join(" / ") : "";
        return (where ? where + "：" : "") + (d.msg || JSON.stringify(d));
      })
    };
  }
  // ...
}
```

還有第三種：根本連不上後端
這時 `fetch` 不會給你狀態碼，而是直接 reject
要另外接，而且訊息要叫使用者去看伺服器還在不在，不能只說「分析失敗」

長度檢查前後端都做
前端擋，是為了不讓使用者白等一趟來回
後端擋，是因為前端的檢查誰都能繞過

### 結果

模型回的是 Markdown
我沒有引套件，只寫了幾十行的簡易渲染：標題、粗體、清單、分隔線
所有文字**先 escape 再轉換**

這件事比看起來重要
模型的輸出對前端來說就是外部輸入，裡面只要有一段 `<img src=x onerror=...>`，直接塞進 `innerHTML` 就會執行
Day 18 要在履歷裡埋攻擊字串，到時候這裡是第一道防線

token 用量跟耗時也放在畫面上，思考 token 另外標顏色
這不是給使用者看的，是給我自己看：每按一次，就知道這次花了多少

<!-- TODO 截圖：用虛構履歷跑出來的結果畫面 -->
<!-- TODO 截圖：錯誤訊息畫面 -->

版本：Python 3.12.10、fastapi 0.141.1、google-adk 2.8.0

## 明天

畫面有了，但我現在的測試方式還是「貼一份履歷、看一下結果、覺得還不錯」
「覺得還不錯」不是一個可以重複的標準

明天先做一批虛構的履歷跟職缺
之後每改一次 prompt，都拿同一批去跑

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
