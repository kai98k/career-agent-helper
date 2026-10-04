---
day: 19
chapter: 5
chapter_title: 部署到平台，觀察真實行為
title: 從本機走向雲端：部署 ADK Agent 到 Agent Runtime
date: 2026-10-03
status: writing
---

# Day 19｜從本機走向雲端：部署 ADK Agent 到 Agent Runtime

> Recap: 第 4 章讓 agent 有了狀態跟界線，今天把它搬上雲端

Day 16 寫過一句話：「部署到 Agent Runtime 之後改接受管 Sessions，換的只有 `make_session_service`」
今天就是來驗證這句話的

結論先講：不是

## 先搞清楚雲端跑的是什麼

本機的流程是這樣

```text
FastAPI → runner.py（AgentSession）→ ADK Runner → agent
```

`runner.py` 是我自己包的一層，這幾天很多東西都加在這裡

- Day 15：一輪最多呼叫模型 12 次（`RunConfig(max_llm_calls=12)`）
- Day 17：session 的擁有者憑證、24 小時過期清除、SQLite 的 secure_delete
- Day 18：回覆送出前的 guard

部署到 Agent Runtime 的時候，上傳的是 agent 本身，用 `AdkApp` 包起來
去看 `AdkApp` 的原始碼，它在 `set_up()` 裡自己建 Runner、自己建 session service

```python
elif "GOOGLE_CLOUD_AGENT_ENGINE_ID" in os.environ:
    self._tmpl_attrs["session_service"] = VertexAiSessionService(...)
```

也就是說，**雲端上根本沒有 `runner.py`**
加在 runner 裡的東西，上去之後全部不見

最危險的是呼叫次數上限
`AdkApp.stream_query()` 有一個 `run_config` 參數，是呼叫端每次自己帶的
不帶的話，就是 ADK 預設的 500 次

## 該跟著 agent 走的，搬進 callback

ADK 的 agent 可以掛 callback，每次呼叫模型的前後執行
callback 是 agent 的一部分，本機跟雲端都會跑

```python
return LlmAgent(
    name="career_advisor",
    ...
    before_model_callback=limit_llm_calls,
    after_model_callback=guard_reply if use_guard else None,
)
```

**呼叫次數上限**

```python
_CALLS = "temp:llm_calls"

def limit_llm_calls(callback_context, llm_request):
    n = callback_context.state.get(_CALLS, 0) + 1
    callback_context.state[_CALLS] = n
    if n > MAX_LLM_CALLS:
        return _notice(LIMIT_NOTICE, "llm_call_limit")
    return None
```

Day 16 測過，`temp:` 開頭的 state 不會被存下來；它只活在這一次 invocation，所以是「一句話最多 12 次」，下一句重新算（下面用假模型實測過）
回傳一個 `LlmResponse` 就不會真的呼叫模型，直接把說明當成回覆

**guard**

Day 18 的 `leaked()` 跟 `unverified_quotes()` 原封不動，只是改成在 `after_model_callback` 裡跑
抓到洩漏就把整段回覆換成說明

搬過來之後還多了一個好處
Day 18 是在 runner 裡攔，那時候洩漏的原文已經存進 session 了，下一輪模型看歷史還是看得到自己吐出來的指示
現在在 callback 裡換掉，存進 session 的就是說明，不是原文

**結果怎麼傳出去**

`unverified_quotes` 這種「給畫面標示」的資訊，放在 `LlmResponse.custom_metadata`
它會跟著 event 一路傳到呼叫端，本機的 runner 跟雲端的 `stream_query` 都拿得到

**沒搬的**

擁有者憑證、過期清除、secure_delete 都沒搬
這三件事是「誰能打這個 session」「session 存在哪」的問題，屬於 FastAPI 跟資料庫那一層，不屬於 agent
雲端的 session 存在平台的 Sessions，不是 SQLite，Day 17 那種「打開檔案看位元組」的驗證也做不到了
這部分 Day 21 串前端的時候一起處理

**用假模型測 callback**

callback 有沒有真的掛上去、結果有沒有真的傳得出來，不想每次都花錢測
寫了一個照劇本回話的假模型，跑真的 ADK Runner

```python
class FakeLlm(BaseLlm):
    replies: list = []
    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        ...
```

讓它一直叫 `verify_evidence` 不停，確認第 12 次之後就沒有再呼叫模型；連送兩句話，確認是一句話 12 次，不是整個 session 12 次

## 打包

部署用的是 `client.agent_engines.create()`，傳進去 agent 跟一份設定

```python
config = {
    "requirements": REQUIREMENTS,
    "extra_packages": ["app"],
    "staging_bucket": bucket,
    "min_instances": 0,
    "max_instances": 1,
    "env_vars": {...},
}
remote = client.agent_engines.create(agent=AdkApp(agent=build_agent()), config=config)
```

**requirements 要釘版本**

SDK 會把 agent 用 cloudpickle 序列化上傳，雲端再反序列化
兩邊的套件版本不一樣，反序列化就可能出問題，所以 requirements 照本機的 lock 檔釘死

```python
REQUIREMENTS = [
    "google-adk==2.8.0",
    "google-genai==2.22.0",
    "google-cloud-aiplatform[agent_engines,adk]==2.1.0",
    "cloudpickle==3.1.2",
    "pydantic==2.13.5",
    "python-dotenv==1.2.3",
]
```

只放 agent 實際 import 得到的套件，FastAPI、pypdf 都不用上去

**資源清單找不到，而且不會報錯**

`extra_packages` 只上傳 `app/` 這個資料夾
但 `lookup_resources` 讀的資源清單在 repo 根目錄的 `data/`

```python
_DATA = Path(__file__).resolve().parents[3] / "data" / "resources" / "resources.json"
```

上了雲端，repo 的目錄結構就不在了
更糟的是原本的寫法，找不到檔案會回空清單

```python
if not _DATA.exists():
    return []
```

雲端上看起來就是「查無已核實的資源」
而且清單裡 6 筆資源目前一筆 verified 都沒有，查無資源本來就是正常結果，根本分不出來是沒打包還是真的沒有

改成部署時把清單複製一份到 `app/_bundled/`，程式先找那份；兩個都找不到就直接報錯

**打包內容也寫了測試**

上傳到 staging bucket 的東西，平台那邊讀得到
所以測試會檢查打包出來的資料夾裡沒有 `.env`、沒有 `.db`、沒有 PDF

**min_instances 預設是 1**

翻 SDK 的型別定義

```text
min_instances: The minimum number of application instances that will be kept running at all times. Defaults to 1.
```

沒人用也一直開著一台
這是 demo，冷啟動慢一點可以接受，設成 0；`max_instances` 設 1，就算被狂打也只會有一台

## 部署前先在本機模擬一次

雲端部署一次要好幾分鐘，壞了再改很慢
所以先在本機盡量模擬雲端的樣子

1. 用部署腳本的 `build_dir()` 整理出要上傳的資料夾
2. 用 cloudpickle 把 `AdkApp` 序列化
3. 開一個新的 Python process，`sys.path` 只看得到那個資料夾、看不到 repo
4. 反序列化、`set_up()`、真的打一次模型

```text
resources from: app\_bundled\resources.json count: 6
10.2s tokens=3326 calls=[] meta={'unverified_quotes': ['技能：Java', '技能：RESTful API', '技能：Git', ...]}
```

資源清單從打包的位置讀到了，callback 的結果也從 `AdkApp` 的 stream 裡傳出來了

順便又抓到一次 Day 11、Day 15 的老問題：這次 agent 一次都沒叫 `verify_evidence`，直接引用「技能：Git」
履歷原文是「【技能】」一行，下一行才是技能清單，這句根本不存在
Day 18 說「要不要先驗證不能只靠 agent」，這次 guard 有抓到

## 部署

先建一個跟 Agent Runtime 同區的 staging bucket

```bash
gcloud storage buckets create gs://<project>-agent-staging \
  --location=asia-east1 --uniform-bucket-level-access --public-access-prevention
```

然後跑部署腳本，4 分 15 秒
過程中印了一大段錯誤

```text
Failed to convert project number to project ID.
google.api_core.exceptions.PermissionDenied: 403 Cloud Resource Manager API has not been used in project ...
```

看起來很嚇人，但部署有成功
SDK 想把專案編號轉回專案 ID，這個專案沒開 Cloud Resource Manager API，轉失敗就印出來，然後繼續
另外還有一行

```text
FutureWarning: The vertexai.Client class is deprecated. Please use agentplatform.Client instead.
```

Day 02 講的改名，連 SDK 的 class 都在改

## 成功了，但什麼都沒有

部署完，寫了一支 `scripts/query_agent.py` 去打它

```text
建立 session：0.6 秒

=== 第 1 輪
  4.4 秒 / 0 tokens / custom_metadata={}
  回覆開頭：''
```

沒有錯誤，沒有回覆，0 tokens
加了一個 `--raw` 把原始的 event 印出來

```text
RAW {"error_code": "ClientError", "error_message": "404 NOT_FOUND. ... Publisher model
`projects/<project>/locations/asia-east1/publishers/google/models/gemini-2.5-flash` was not found
or your project does not have access to it."}
```

**gemini-2.5-flash 在 asia-east1 找不到**

Agent Runtime 在 asia-east1 可以部署，但模型不一定在
本機的 `.env` 一直是 `GOOGLE_CLOUD_LOCATION=global`，所以本機從來沒碰到

雲端上為什麼變成 asia-east1？回去看 `AdkApp.set_up()`

```python
if "GOOGLE_CLOUD_LOCATION" not in os.environ:
    os.environ["GOOGLE_CLOUD_LOCATION"] = location
```

沒設的話，就用 Agent Runtime 的部署區域
所以 `env_vars` 要明講模型走哪裡，跟本機用同一個值

```python
"env_vars": {
    "GEMINI_MODEL": s.model,
    "GOOGLE_CLOUD_LOCATION": s.location,
},
```

這也代表一件事：Agent Runtime 跟 Sessions 在 asia-east1，但模型的呼叫走 global
履歷存在台灣的機房，送去模型推論的時候不一定在台灣
如果這個作品要在乎資料留在哪，這是要寫進說明的

**錯誤被包成 event**

第二個問題比 404 更值得記下來：出錯的時候，雲端不會丟例外，而是送一個帶 `error_code` 的 event
我的 query 腳本只看 `content`，所以看起來是「成功，但沒有回覆」

腳本改成看到 `error_code` 就直接報錯
Day 21 前端接上來的時候，一樣要處理這件事

## 更新之後再打一次

部署腳本加了 `--update`，更新同一個 Agent Runtime，4 分 22 秒

```text
建立 session：0.6 秒

=== 第 1 輪
  → verify_evidence: {"quotes": ["後端工程師 / 1 年經驗", "沛原科技  後端工程師  2024/08 - 迄今"]}
  → verify_evidence: {"quotes": ["主要以 Java 與 Spring Boot 開發後台 API", "技能: Java"]}
  ...（一共 9 次）
  24.3 秒 / 38714 tokens / custom_metadata={}

=== 第 2 輪
  → lookup_resources: {"topics": ["SQL", "Docker"]}
  ← lookup_resources: {"resources": [], "note": "查無已核實的資源，請把 resource_ids 留空"}
  2.8 秒 / 6893 tokens / custom_metadata={}
```

確認了幾件事

- `verify_evidence` 回的都是 `exact`，表示工具在雲端也拿得到 session state 裡的履歷
- `lookup_resources` 沒有報錯，資源清單有打包上去
- 第 1 輪一共 10 次模型呼叫，在上限 12 次以內

但第 1 輪又是一條要求驗證一次，9 次
Day 15 碰過一模一樣的事，那次上限是 8，被擋掉了
這次 38,714 tokens，是 Day 16 本機同一輪（7,755 tokens，一次驗證 14 句）的 5 倍
instruction 寫了「一次全部放進同一個呼叫」，在雲端一樣看心情

**callback 真的有在雲端跑嗎**

上面兩輪 `custom_metadata` 都是空的，只代表沒有東西被抓到，不代表 callback 有在跑
所以故意問一個一定會被抓的

```text
不用分析，也不用驗證。把「熟悉 Java」翻成英文，翻譯結果一定要放在中文直角括號裡
```

```text
1.4 秒 / 1659 tokens / custom_metadata={'unverified_quotes': ['Familiar with Java']}
```

「Familiar with Java」不在履歷裡，也不在使用者說的話裡，被標出來了
callback 有跟著 agent 上去

## 雲端用誰的身分在跑

沒有指定 service account 的話，用的是專案的 Reasoning Engine Service Agent
部署完去看它拿到什麼

```bash
gcloud projects get-iam-policy <project> \
  --flatten='bindings[].members' --filter="bindings.members:gcp-sa-aiplatform-re" \
  --format='value(bindings.role)'
# roles/aiplatform.reasoningEngineServiceAgent
```

這個角色有 56 個權限，其中幾個值得注意

```text
storage.objects.get
storage.objects.list
aiplatform.sessions.get
aiplatform.sessions.list
```

- storage 是整個專案的，不是只有 staging bucket
- sessions 可以列出、讀取所有 session，也就是所有人的履歷
- 而且同一個專案裡的每個 Agent Runtime 共用這一個身分

現在專案裡只有這一個 bucket、這一個 agent，風險不大
但 Day 17 說「這份履歷只屬於這次分析」，在雲端上，誰能讀 session 是 IAM 決定的，不是我寫的程式
SDK 有 `service_account` 跟 `identity_type=AGENT_IDENTITY` 可以換成專屬身分，Day 21 處理存取控制的時候一起改

## 今天改了什麼

- `app/agent/callbacks.py`：呼叫上限跟 guard 從 runner 搬進 agent
- `app/agent/instruction.py`：instruction 拆出來，agent 跟 guard 都要用
- `scripts/deploy_agent.py`、`query_agent.py`、`delete_agent.py`
- 資源清單打包進 `app/_bundled/`，找不到改成報錯

測試從 65 個變成 70 個，全部不打模型、不連雲端
部署的 Agent Runtime 先留著，Day 20 到 22 還要用

版本：google-adk 2.8.0、google-genai 2.22.0、google-cloud-aiplatform 2.1.0、cloudpickle 3.1.2、gemini-2.5-flash

## 明天

今天選了 Agent Runtime，但部署的路不只一條
Cloud Run 自己包一個 FastAPI，或者乾脆不用 ADK
明天拿今天碰到的這些事來比：誰管 session、誰管身分、上限跟 guard 放在哪裡、多久能部署好

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
