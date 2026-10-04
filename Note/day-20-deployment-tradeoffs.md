---
day: 20
chapter: 5
chapter_title: 部署到平台，觀察真實行為
title: Agent Runtime、Cloud Run 還是自己包？部署路徑的取捨
date: 2026-10-04
status: writing
---

# Day 20｜Agent Runtime、Cloud Run 還是自己包？部署路徑的取捨

> Recap: 昨天把 agent 部署到 Agent Runtime，今天走另一條路，把同一個 agent 放上 Cloud Run 比一比

ADK 的 agent 要上雲端，常見的有三條路

| 路徑 | 做法 |
| --- | --- |
| Agent Runtime | `client.agent_engines.create()`，平台幫你跑 agent、管 session |
| Cloud Run（ADK 幫你包） | `adk deploy cloud_run`，ADK 產生 Dockerfile，跑它內建的 `adk api_server` |
| 自己包 | 自己寫 Dockerfile 跟 API，放上 Cloud Run 或任何地方 |

前兩條今天都實際部署了，同一份 agent、同一個區域（asia-east1）、同樣 `min-instances=0`、`max-instances=1`
第三條沒有部署，只拿前兩條碰到的事來推，後面會講清楚哪些是推的

## 先看 adk deploy cloud_run 做了什麼

部署之前先翻原始碼，`google/adk/cli/cli_deploy.py` 裡有一段 Dockerfile 的樣板

```dockerfile
FROM python:3.11-slim
...
ENV GOOGLE_CLOUD_LOCATION={gcp_region}
...
RUN pip install "google-adk[a2a]=={adk_version}"
...
COPY --chown=myuser:myuser "agents/{app_name}/" "/app/agents/{app_name}/"
...
CMD adk api_server --port={port} ... "/app/agents"
```

光看這段就有三個要注意的地方

- `python:3.11-slim`：本機跟 Agent Runtime 都是 3.12
- `GOOGLE_CLOUD_LOCATION` 設成部署區域：跟昨天一樣，gemini-2.5-flash 在 asia-east1 會 404
- 只複製 agent 那個資料夾：同一個檔案裡 `extra_packages_copy=''` 寫死，Cloud Run 這條路不支援 extra_packages

還有 session，`--session_service_uri` 不給的話是 `memory://`
instance 縮到 0 就全部不見，有兩台的時候各自一份
這裡接到昨天 Agent Runtime 的 Sessions（`agentengine://...`），兩條路共用同一個存放處，比較時才不會多一個變數

## 包一個資料夾給它

我們的 agent 在 `app/agent/agent.py`，會 import `app.services...`
`adk deploy` 只複製 agent 資料夾，所以要另外包一個

```text
career_advisor/
├── __init__.py        from . import agent
├── agent.py           把 app/ 加進 sys.path，再 from app.agent.agent import root_agent
├── requirements.txt
└── app/               昨天部署用的同一份（含 _bundled/resources.json）
```

`scripts/deploy_cloud_run.py` 負責包資料夾，再呼叫 `adk deploy cloud_run`

```python
cmd = [
    "adk", "deploy", "cloud_run",
    "--project", project,
    "--region", region,
    "--service_name", "career-agent-helper",
    "--app_name", "career_advisor",
    "--session_service_uri", f"agentengine://{engine}",
    str(folder),
    "--",
    "--no-allow-unauthenticated",
    "--min-instances=0",
    "--max-instances=1",
    f"--set-env-vars=GOOGLE_CLOUD_LOCATION={s.location},GEMINI_MODEL={s.model}",
    f"--service-account=career-agent-run@{project}.iam.gserviceaccount.com",
    "--quiet",
]
```

`--` 後面的參數會原樣交給 `gcloud run deploy`
`--set-env-vars` 蓋掉 Dockerfile 裡的 `GOOGLE_CLOUD_LOCATION`，昨天的 404 不用再踩一次

部署之前先在本機用 `adk api_server` 跑這個資料夾，確認包裝沒問題
順便發現一件事：建立 session 的 API 有兩個，網址帶 session id 的那個，body 直接就是 state；不帶的那個，body 是 `{"state": {...}}`
我第一次送錯，履歷被存成一個叫 `state` 的 key，instruction 的 `{resume_text}` 找不到，回 500

## 部署：失敗三次

**第一次：建置的權限不夠**

```text
ERROR: (gcloud.run.deploy) PERMISSION_DENIED: Build failed because the default service account
is missing required IAM permissions.
... IAM permission denied for service account <number>-compute@developer.gserviceaccount.com.
```

`gcloud run deploy --source` 會用 Cloud Build 建 image，建置用的是 Compute Engine 的預設 service account
新的專案不會再自動給它很大的權限，照官方文件給它 `roles/run.builder`

然後發現另一件事：我的部署腳本印出來是 `exit=0`
`adk deploy` 失敗的時候會印「Deploy failed」，但 exit code 還是 0
這是這兩天第三個「失敗了但說自己成功」的工具（昨天是 Agent Runtime 把錯誤包成 event、SDK 印了一堆錯誤但部署其實成功），所以腳本最後改成自己去問 Cloud Run 這個服務有沒有起來

```python
url = subprocess.run(
    [gcloud, "run", "services", "describe", SERVICE, "--region", region,
     "--project", project, "--format=value(status.url)"],
    capture_output=True, text=True,
).stdout.strip()
if not url:
    raise SystemExit("Cloud Run 上找不到這個服務，部署其實失敗了，往上看 adk 的輸出")
```

**第二次：容器起不來**

```text
The user-provided container failed to start and listen on the port defined provided by the PORT=8000
```

去看 Cloud Run 的 log

```text
File ".../google/adk/sessions/vertex_ai_session_service.py", line 148, in __init__
    import vertexai  # noqa: F401
ModuleNotFoundError: No module named 'vertexai'
```

session 接 `agentengine://` 要用到 `google-cloud-aiplatform`，但 ADK 產生的 Dockerfile 只裝 `google-adk[a2a]`
`--session_service_uri` 是 ADK 自己的選項，選了它，它卻沒幫你裝需要的套件
我在 requirements.txt 把 aiplatform 排除掉了（以為 Dockerfile 會裝），加回來

**第三次：部署成功，但一跑就 500**

```text
SyntaxError: Fail to load 'career_advisor' module. invalid syntax
```

就是 `python:3.11-slim`
用 3.11 的語法規則把整個 `app/` 掃一次

```python
ast.parse(source, feature_version=(3, 11))
```

```text
app\services\llm.py:44: Type parameter lists are only supported in Python 3.12 and greater
    class Result[TModel: BaseModel]:
```

固定流程呼叫模型的 `llm.py`，泛型用了 3.12 的新語法
本機是 3.12、Agent Runtime 用的是部署那台電腦的 Python 版本（也是 3.12），所以昨天完全沒事
`adk deploy cloud_run` 沒有選項可以換 base image，要嘛改程式，要嘛自己寫 Dockerfile（那就是第三條路了）

改回 3.11 也能跑的寫法

```python
@dataclass
class Result(Generic[T]):
    data: T
```

這個掃描也寫成測試了，本機的測試都在 3.12 上跑，不寫的話永遠不會發現

**第四次成功**

```text
Service [career-agent-helper] revision [career-agent-helper-00002-pbx] has been deployed and is serving 100 percent of traffic.
```

## 跑起來之後

```text
沒帶身分：403
建立 session：2.8 秒
第 1 輪：14.4 秒 / 4439 tokens / 0 次工具呼叫
  custom_metadata={'unverified_quotes': ['校園二手書交換平台（畢業專題，2023/09 - 2024/05）- 以 Spring Boot 實作書籍上架、搜尋與媒合通知 - 負責後端全部功能', '專案詳情', '技術說明']}
從 Agent Runtime 讀同一個 session：2 個 event，state=['resume_text']
```

幾件事

- 沒帶身分的請求被擋下來，`--no-allow-unauthenticated` 有生效
- 在 Cloud Run 建的 session，用 Agent Runtime 的 API 讀得到，兩條路真的共用同一個存放處
- 昨天搬進 callback 的 guard 在 Cloud Run 上也有跑：這輪 agent 一次都沒驗證，guard 把三行合成一句的「引用」標出來了

最後一點是昨天那個決定的回報
如果 guard 還留在 `runner.py`，換成 Cloud Run 一樣會不見；放在 agent 上，不管誰來跑都帶著

## 比較

| | Agent Runtime | Cloud Run（adk deploy） |
| --- | --- | --- |
| 部署時間 | 4 分 15 秒（更新 4 分 22 秒） | 7 分 8 秒（建 image 約 1 分 45 秒） |
| 失敗幾次才成功 | 1 次（模型 404） | 3 次 |
| Python 版本 | 跟部署的電腦一樣（3.12） | 寫死 3.11 |
| 打包方式 | pickle agent + extra_packages | Docker image（172 MB） |
| session | 平台管 | 預設記憶體，要自己接 |
| 冷啟動：建 session | 36.5 秒 | COLD_CREATE |
| 冷啟動：第一個回覆 | 29.9 秒 | COLD_RUN |
| 熱的：建 session + 回覆 | 0.4 + 2.1 秒 | WARM |
| 誰能呼叫 | 有 Agent Platform 權限的人 | 有 `run.invoker` 的人 |
| 跑 agent 的身分 | 專案共用的 service agent（56 個權限） | 自己指定 |
| 呼叫方式 | SDK 的 `stream_query` | 一般的 HTTP API |

冷啟動是同一句短訊息（「不用分析，用一句話告訴我你能幫我做什麼。」），閒置一段時間之後打第一次，再連打兩次

**冷啟動**

Agent Runtime 是放了一整晚之後量的，光建 session 就 36.5 秒，第一個回覆再 29.9 秒，使用者等了一分鐘
`min_instances=0` 確實有縮到 0，代價就是這一分鐘

COLD_NOTE

**身分：自己指定不等於權限比較小**

Cloud Run 可以用 `--service-account` 指定一個專屬帳號，昨天 Agent Runtime 用的是整個專案共用的 service agent
看起來 Cloud Run 比較好控制，但我給它的 `roles/aiplatform.user` 有 451 個權限，比 service agent 的 56 個還多
裡面一樣有 `aiplatform.sessions.list`，一樣讀得到所有人的 session
真的要收小，得自己做 custom role

**API：網址裡就有 user_id**

`adk api_server` 的 session API 長這樣

```text
GET /apps/career_advisor/users/{user_id}/sessions/{session_id}
```

本機試過，知道別人的 user_id 跟 session id，就能把那個人 session 的 state 整份拿走，履歷就在裡面
所以 `--no-allow-unauthenticated` 不是選配
但就算擋住了未驗證的請求，拿得到 `run.invoker` 的人一樣可以換 user_id 讀別人的
Day 17 的擁有者憑證是寫在我們自己的 FastAPI 裡，不在這兩條路的任何一條上

## 第三條路：自己包

這條沒有部署，以下是從前兩條碰到的事推出來的

自己寫 Dockerfile，跑我們自己的 FastAPI（就是本機一直在用的那個），放上 Cloud Run

- Python 版本、base image、裝什麼套件，全部自己決定，今天的第二、第三次失敗都不會發生
- Day 17 的擁有者憑證、Day 18 的 API 回傳格式，原封不動帶上去
- 但 session 要自己找地方放：SQLite 在 Cloud Run 上活不過 instance 重啟，要嘛接 Cloud SQL / Firestore，要嘛一樣接 `agentengine://`
- Day 17 的 secure_delete、過期清除，換了資料庫就要重做一次

## 這個作品的選擇

三條路的差別，說穿了是「誰負責哪一層」

- 跑 agent、管 session：Agent Runtime 最省事，部署最快、失敗最少
- 誰能看哪一份履歷：三條路裡，只有「自己包」的那層 FastAPI 做得到每個使用者只能碰自己的 session

所以接下來的架構是兩條混著用：agent 留在 Agent Runtime，前面放我們自己的 FastAPI 當門口，處理身分跟擁有者
Cloud Run（adk deploy）這條測完就收掉

## 收拾

依照今天一開始講好的，測完刪掉

```bash
gcloud run services delete career-agent-helper --region asia-east1
gcloud artifacts docker images delete asia-east1-docker.pkg.dev/<project>/cloud-run-source-deploy/career-agent-helper --delete-tags
```

為了部署開的權限也收回來：`roles/run.builder`、專屬的 `career-agent-run` 帳號跟它的 `roles/aiplatform.user`
API 留著，開著不收錢

測試從 70 個變成 71 個，多的是那個 3.11 語法掃描

版本：google-adk 2.8.0、google-genai 2.22.0、google-cloud-aiplatform 2.1.0、gemini-2.5-flash、Cloud Run（python:3.11-slim）

## 明天

今天的結論是：門口要自己顧
明天把網頁接到雲端的 agent，前面那層 FastAPI 要決定「你是誰」「你能碰哪個 session」，然後把 `unverified_quotes` 這些結果呈現在畫面上

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
