---
day: 16
chapter: 4
chapter_title: 讓 Agent 有狀態，也有界線
title: 讓對話延續：用 Sessions 保存澄清答案與計畫修訂
date: 2026-09-30
status: writing
---

# Day 16｜讓對話延續：用 Sessions 保存澄清答案與計畫修訂

> Recap: 昨天把工具參數改成有型別，計畫第一次就驗證通過，但對話全部存在記憶體裡

Day 14 說 agent 值得存在的理由，是它可以「聽完回答再決定下一步」
使用者說 SQL 有寫過，計畫裡就不排 SQL 入門

可是這件事有個前提：它要記得使用者說過什麼
現在這份記憶放在哪裡？

```python
self._sessions = session_service or InMemorySessionService()
```

放在 Python 的一個 dict 裡
今天先把這件事搞清楚，再決定要換成什麼

## 重開服務，對話就沒了

先確認一下「在記憶體裡」到底是什麼意思
開一個 session，再開一個新的 `InMemorySessionService` 去拿

```python
a = InMemorySessionService()
s = await a.create_session(app_name=APP, user_id="u1", state={"resume_text": "..."})

b = InMemorySessionService()
await b.get_session(app_name=APP, user_id="u1", session_id=s.id)
# → None
```

新的 instance 什麼都沒有
服務重開就是這個情況，uvicorn 開 `--reload` 的話，存檔一次就重開一次

使用者回答完澄清問題、排好計畫，我改一行 code，這些全部不見
下次再進來，agent 又從「請問您有沒有用過關聯式資料庫」開始問

## Session 裡到底存了什麼

ADK 的 session 分兩塊

| | 是什麼 | 這個專案放什麼 |
| --- | --- | --- |
| `events` | 每一則訊息、每一次工具呼叫與結果，照順序 | 使用者的回答、agent 的回覆、`validate_learning_plan` 的每一次結果 |
| `state` | 一個 key-value 的 dict | 確認過的履歷全文 |

標題寫的兩件事，其實都已經在 `events` 裡了

- 澄清答案：使用者回的「SQL 有寫過」就是一則 user event
- 計畫修訂：agent 每送一次 `validate_learning_plan`，參數跟 violations 都是 event

ADK 每次呼叫模型，預設會把整串 events 一起送過去，所以 agent 才「記得」
也就是說，要讓對話延續，重點不是多存什麼，而是**讓這些東西活過重開**

## 第一個坑：直接改 state 不會存

一開始想說，那澄清答案另外整理一份放進 state，之後要用比較好拿

```python
got = await svc.get_session(app_name=APP, user_id="u1", session_id=sid)
got.state["clarify_answers"] = {"SQL": "有寫過"}

again = await svc.get_session(app_name=APP, user_id="u1", session_id=sid)
"clarify_answers" in again.state
# → False
```

沒存進去
`get_session` 拿到的是一份複本，改它不會寫回去，InMemory 跟資料庫版都一樣

ADK 的規則是：state 只能透過 event 改
要嘛在 event 上帶 `state_delta`，要嘛在工具裡寫 `tool_context.state[...]`，ADK 會幫你轉成 `state_delta`

```python
Event(
    author="user",
    invocation_id="i1",
    content=...,
    actions=EventActions(state_delta={"clarify_answers": {"SQL": "有寫過"}}),
)
await svc.append_event(session, event)
```

這樣設計的好處是，state 每一次怎麼變，都有一個 event 可以回頭查
Day 22 用 Trace 看「計畫改了幾次、每次為什麼改」會用到

## state 的 key 有前綴

翻文件才知道 state 的 key 前綴是有意義的

| 前綴 | 範圍 |
| --- | --- |
| （無） | 只在這個 session |
| `user:` | 同一個 user 的所有 session 共用 |
| `app:` | 整個 app 共用 |
| `temp:` | 只活在這一次呼叫，不會存 |

實際測一次，同一個 event 裡帶三種 key

```python
state_delta={
    "clarify_answers": {"SQL": "有寫過"},
    "user:weekly_hours": 6,
    "temp:scratch": 1,
}
```

存完之後，同一個 user 再開一個新 session

```python
{'user:weekly_hours': 6}
```

`user:` 的會跟過來，`temp:` 的沒被存，沒前綴的只留在原本那個 session

看到這裡第一個反應是：每週時數放 `user:`，下次開新分析就不用再問一次，很方便
但想了一下還是沒這樣做

Day 17 的標題是「這份履歷只屬於這次分析」
如果每週時數可以跨 session，下一步很自然就會想把履歷也放 `user:`，那 session 刪掉了，履歷還在
所以現在的規則是：**這個專案不用 `user:` 跟 `app:`**，一次分析的東西，就只活在那一個 session 裡

## 換成資料庫

本機要活過重開，最簡單的是 `DatabaseSessionService` 加 SQLite
照 runner 開頭註解寫的，換的只有一行

```python
DatabaseSessionService(db_url="sqlite+aiosqlite:///./sessions.db")
```

結果第一次就炸了

```text
ImportError: The 'sqlalchemy' package is required to use this feature.
Please install it by running: pip install google-adk[db]
```

好，照它說的裝
ADK 的 `[db]` extra 會帶 `SQLAlchemy`，跑 dry-run 看一下會裝什麼

```text
Would install ... SQLAlchemy-2.1.1 alembic-1.20.0 sqlalchemy-spanner-1.20.1 ...
```

裝完再跑，換了一個錯誤

```text
NameError: name 'create_async_engine' is not defined
...
ValueError: Failed to create database engine for URL 'sqlite+aiosqlite:///...'
```

看訊息會以為是 URL 寫錯，在路徑上查了一陣子
其實是 ADK 的這段

```python
try:
    ...
    from sqlalchemy.ext.asyncio import create_async_engine
    ...
except ImportError:
    pass
```

import 失敗被吞掉了，自己 import 一次才看到真正的原因

```text
ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed.
```

SQLAlchemy 2.1 把 `greenlet` 改成 `[asyncio]` extra 才會裝，ADK 2.8.0 的 `[db]` 要的是 `sqlalchemy>=2`，沒有帶 `[asyncio]`
所以照錯誤訊息裝完，還是跑不起來

requirements 要自己補

```text
google-adk[db]>=2.0
sqlalchemy[asyncio]>=2
```

runner 那邊，存哪裡改成從設定讀，留空就退回記憶體版

```python
def _default_session_service() -> BaseSessionService:
    url = get_settings().session_db_url
    if not url:
        return InMemorySessionService()

    from google.adk.sessions import DatabaseSessionService

    # SQLite 不會自己建資料夾
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        Path(url.removeprefix(prefix)).parent.mkdir(parents=True, exist_ok=True)
    return DatabaseSessionService(db_url=url)
```

預設存在 `backend/.sessions/sessions.db`
這個檔案裡有使用者貼的履歷，資料夾先加進 `.gitignore`，Day 05 的 `adk web` 也在 agent 目錄底下自己建了一個 `.adk/`，一樣的理由

## 重開之後還在

裝好之後，用一個 `DatabaseSessionService` 寫入，再開一個新的去讀，模擬服務重開

```python
d1 = DatabaseSessionService(db_url=url)
# 建 session、append 一個帶 state_delta 的 event

d2 = DatabaseSessionService(db_url=url)
r = await d2.get_session(app_name=APP, user_id="u1", session_id=sid)
```

```text
state:  {'resume_text': '...', 'clarify_answers': {'SQL': '有寫過'}, 'user:weekly_hours': 6}
events: 1
```

state 跟 event 都在
順便試了一下拿別人的 session

```python
await d2.get_session(app_name=APP, user_id="u2", session_id=sid)
# → None
```

session id 對了，user 不對，一樣拿不到
這是 Day 17 使用者隔離的基礎，但只靠這個夠不夠，明天再說

這三件事都寫成測試了，不打模型，測試從 44 個變成 47 個

## 真的打模型跑一次

一樣用 Day 14 的兩輪對話，再加一輪改計畫
每一輪都是一個獨立的 Python process，跑完就結束，下一輪重新 `AgentSession()`、重新連資料庫，等於每一輪之間都重開一次服務

1. 「我想應徵下面這個職缺，幫我看看履歷跟它的落差。」加上職缺全文
2. 「SQL 有寫過，在學校專題用 MySQL 寫過查詢；Docker 只有在自己電腦跑過 MySQL。我每週可以花 6 小時，請幫我排學習計畫。」
3. 「第二週我要出差，那週只有 2 小時，其他週不變，幫我調整計畫。」

**第一輪**

```text
[before] events=0 state_keys=['resume_text']
tool_calls: ["verify_evidence"]  llm_calls: 2  total_tokens: 7,755  20.3 秒
```

先講一個意外的收穫
Day 15 它一條要求叫一次 `verify_evidence`，叫了 8 次被上限擋掉；加了「一次全部放進同一個呼叫」之後，那次反而一個都沒驗
這次它 14 句一次送進去，全部 `exact`，然後才回覆
同一段 instruction，這次有照做，也再次說明靠 instruction 就是不穩定，Day 15 記下來的事還是要做

回覆最後問了兩題：SQL 有沒有實際寫過、Docker 或 CI/CD 有沒有碰過
這次沒有再誤報 prompt injection

**重開，第二輪**

```text
[before] events=4 state_keys=['resume_text']
tool_calls: ["lookup_resources", "validate_learning_plan"]  llm_calls: 3  total_tokens: 18,223  18.0 秒
```

新的 process 一進來，session 裡已經有 4 個 event：使用者的訊息、驗證的呼叫、驗證的結果、回覆
它記得自己問過什麼

排出來的計畫

| 週 | 主題 | 時數 |
| --- | --- | --- |
| 1 | SQL 資料庫設計與正規化 | 6 |
| 2 | SQL 索引優化與效能調校 | 6 |
| 3 | Docker 容器化基礎與實踐 | 6 |

使用者說 SQL 寫過，所以沒有 SQL 入門，從資料表關聯跟索引開始，剛好對上職缺寫的「理解資料表關聯與索引用途」
Docker 那週的理由寫的是「從您的現有基礎（在個人電腦跑過 MySQL）進一步學習」
這兩件事都是上一個 process 裡使用者講的

`validate_learning_plan` 第一次就 `ok: true`，昨天改的型別還是有效

**重開，第三輪：改計畫**

```text
[before] events=10 state_keys=['resume_text']
tool_calls: ["validate_learning_plan"]  llm_calls: 2  total_tokens: 18,082  18.1 秒
```

這一輪它沒有重新查資源、也沒有重排，直接拿上一版改
送進驗證工具的計畫，第一週的 `rationale` 跟上一版一字不差，因為上一版的工具參數就存在 event 裡

| 週 | 主題 | 時數 |
| --- | --- | --- |
| 1 | SQL 資料庫設計與正規化 | 6 |
| 2 | SQL 索引優化與效能調校 (I) | 2 |
| 3 | SQL 索引優化與效能調校 (II) | 4 |
| 4 | Docker 容器化基礎與實踐 | 6 |

第二週只剩 2 小時，它把索引拆成兩半，Docker 往後推一週，總時數一樣 18
驗證也是 `ok: true`

但仔細看，第三週只排了 4 小時
使用者說的是「其他週不變」，原本第三週是 6 小時的 Docker，現在變成 4 小時的索引
它的理解是「總量不變、內容往後推」，這也說得通，但不是使用者講的那樣
驗證工具只檢查「每週不超過預算」，不會檢查「有沒有照使用者說的改」，這種落差程式抓不到，Day 25 定評估規準的時候要放進去

標題說的「保存澄清答案與計畫修訂」，到這裡算是做到了
而且不用另外設計欄位，答案跟每一版計畫，本來就在 events 裡

## 順便發現：履歷每一次都有送

runner 開頭的註解是 Day 14 寫的

> 履歷放進 session state 而不是每次都塞進訊息裡，有兩個理由：一是省 token，二是工具取用的永遠是同一份確認過的文字

第二個理由成立，第一個不成立

instruction 最後一段長這樣

```text
## 使用者的履歷

{resume_text}
```

`{resume_text}` 是 ADK 的 state 注入，每次呼叫模型之前，會從 state 把履歷填進 system instruction
用 `count_tokens` 量了一下

| | 字數 | tokens |
| --- | --- | --- |
| 履歷 | 621 | 387 |
| instruction（不含履歷） | 960 | 589 |

上面三輪一共 7 次模型呼叫，履歷就送了 7 次，大約 2,700 tokens

放在 state 沒有省到 token，省的是「履歷只有一個來源」
agent 看到的、工具拿來比對的，是同一份文字，這才是它真正的價值
註解已經改掉了

## 真正在長大的是 events

履歷每次 387 tokens，是固定的
會一直變大的是對話本身

把 session 裡每一次模型呼叫的 `prompt_token_count` 撈出來

| 輪 | 那一次在做什麼 | prompt tokens |
| --- | --- | --- |
| 1 | 決定要驗證哪些句子 | 1,713 |
| 1 | 拿到驗證結果，寫回覆 | 3,551 |
| 2 | 查資源 | 4,568 |
| 2 | 送驗證計畫 | 5,649 |
| 2 | 寫回覆 | 6,000 |
| 3 | 改計畫、送驗證 | 6,627 |
| 3 | 寫回覆 | 8,685 |

第三輪只講了一句「第二週只有 2 小時」，模型一次就要讀 8,685 tokens，前兩輪的分析、驗證結果、整份計畫全部重送一次
三輪的 prompt tokens 加起來 36,793，履歷只佔 7% 左右

所以要省，該動的不是履歷，而是舊的 events：舊版計畫、已經用過的驗證結果，要不要一直帶著
ADK 有 `include_contents` 可以整個不帶歷史，但那樣它就不記得使用者說過什麼了，等於回到 Day 11 只能問一輪
現在三輪、不到 9K，還不急，但 session 沒有上限，這個先記下來，Day 29 算成本的時候一起看

## 部署之後

本機用 SQLite，Day 19 部署到 Agent Runtime 之後改接受管的 Sessions（`VertexAiSessionService`）
一樣是 `BaseSessionService`，`AgentSession` 本來就可以從外面傳進來，其他程式不用動

只是要記得 Day 14 提過的：ADK 2.0 的 Event 多了欄位，**不要接 1.x 留下來的 session 資料庫**
這個專案從一開始就是 2.x，沒有這個問題，但照舊教學先建好資料庫的人要注意

版本：google-adk 2.8.0、google-genai 2.22.0、SQLAlchemy 2.1.1、greenlet 3.5.6、aiosqlite 0.22.1、gemini-2.5-flash

## 明天

session 現在活得過重開了，但這也代表履歷會一直留在硬碟上
今天跑完這三輪，`sessions.db` 裡就躺著一份完整的履歷、三輪對話、兩版計畫
`DELETE /agent/sessions/{id}` 這個端點 Day 14 就寫好了，可是刪掉之後，SQLite 檔裡真的沒有了嗎？
明天處理使用者隔離、資料保留與刪除

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
