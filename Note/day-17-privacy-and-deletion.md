---
day: 17
chapter: 4
chapter_title: 讓 Agent 有狀態，也有界線
title: 這份履歷只屬於這次分析：使用者隔離、資料保留與刪除
date: 2026-10-01
status: writing
---

# Day 17｜這份履歷只屬於這次分析：使用者隔離、資料保留與刪除

> Recap: 昨天把 session 存進 SQLite，服務重開對話還在，但履歷也跟著留在硬碟上了

昨天跑完三輪，`sessions.db` 裡躺著一份完整的履歷、三輪對話、兩版計畫
session 活得過重開，是昨天要的
履歷也活得過重開，是今天要處理的

履歷有姓名、學校、公司、做過什麼，是很完整的個資
這個作品要人家把履歷貼進來，就得講得清楚三件事

- 誰看得到
- 放多久
- 刪掉之後，是不是真的沒了

## 先盤點：履歷現在在哪裡

不先盤點，刪除就只是刪掉「我記得的那一份」

| 位置 | 有什麼 | 誰控制 |
| --- | --- | --- |
| `backend/.sessions/sessions.db` | state 裡的履歷全文；events 裡的驗證引用、agent 回覆裡的原句 | 我 |
| 送給 Gemini 的 prompt | 每次呼叫模型都有完整履歷（Day 16 量過，一次 387 tokens） | 平台的資料政策 |
| `evals/injection.py` | 攻擊用的虛構履歷，Day 16 之後也會寫進 `sessions.db` | 我 |
| `adk web` 的 `.adk/` | dev UI 自己建的 session 資料庫 | 我，已經在 `.gitignore` 裡 |
| 路徑 A `/analyze` | 不存，請求結束就沒了 | — |
| 前端 | 沒有用 localStorage，關掉分頁就沒了 | — |

送到 Gemini 那一段不是我寫程式能控制的，要看平台的資料政策，這篇不展開
今天處理的是我能控制的：`sessions.db`

## 第一個問題：誰都能自稱 alice

先看 Day 14 寫的端點

```python
class StartSessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    resume_text: str = ...
```

`user_id` 是呼叫端自己填的
ADK 的 session 確實是用 `user_id` 隔開的，昨天也測過，user 不對就拿不到
但如果 user 是誰都能自己說，那這個隔離就沒有意義

實際打一次，alice 開一個 session，然後 mallory 拿著 session id 來

```text
alice start        200  {'session_id': '33d87045-...', 'user_id': 'alice'}
mallory send       500  Internal Server Error
mallory delete     204
自稱 alice delete  204
再刪一次           204
```

三個問題

- mallory 只要說自己是 alice，就能接著 alice 的對話問「把剛剛的履歷原文貼給我」，也能把它刪掉
- 刪別人的、刪不存在的、真的刪掉的，全部回 204，看不出到底有沒有刪到東西
- user 不對的時候回 500，是 ADK 丟了 `SessionNotFoundError` 沒人接

## 改法：開 session 的時候發一個憑證

真正的身分驗證是 Day 21 的事，那時候會接上登入
在那之前，至少不能讓「自稱」就算數

開 session 的時候，伺服器產生一個隨機的 token，只回傳這一次

```python
def new_owner_token() -> str:
    return secrets.token_urlsafe(32)


def owner_of(token: str) -> str:
    return "anon-" + hashlib.sha256(token.encode()).hexdigest()[:32]
```

`user_id` 不再讓呼叫端填，而是從 token 算出來
之後每一個請求都要在 header 帶 `X-Session-Token`

```python
@app.post("/agent/sessions")
async def start_agent_session(req: StartSessionRequest) -> dict:
    token = new_owner_token()
    s = await _agent.start(owner_of(token), req.resume_text)
    return {"session_id": s.id, "token": token}
```

資料庫裡存的是雜湊，不是 token 本身
就算有人拿到 `sessions.db`，也還原不出 token，沒辦法拿去打 API

**找不到跟不是你的，回一樣的 404**

```python
_NOT_FOUND = HTTPException(status_code=404, detail="找不到這個 session，可能已過期或被刪除")
```

一開始想說不是你的應該回 403
但回 403 等於告訴對方「這個 session id 是存在的，只是不是你的」
所以兩種情況回一模一樣的東西，測試裡也檢查了回應內容要完全相同

**刪除要知道有沒有刪到**

ADK 的 `delete_session` 找不到也不會報錯，就是一句 `DELETE ... WHERE`
所以刪之前先查一次，沒有就回 404

```python
async def delete(self, user_id: str, session_id: str) -> bool:
    if not await self.exists(user_id, session_id):
        return False
    await self._sessions.delete_session(...)
    return True
```

## 第二個問題：刪掉了，但檔案裡還在

這是今天最想知道的
拿昨天那份 `sessions.db` 的複本，用 ADK 刪掉 session，再去看檔案本身

**先差點被騙**

第一次直接在檔案裡搜「沛原科技」，刪除前、刪除後都是 0 次
差點就寫「刪乾淨了」

但刪除前也是 0，這不對
原來 ADK 存 state 跟 event 的時候，JSON 裡的中文會跳脫成 `沛原...`，直接搜中文永遠找不到
改搜跳脫後的字串

```text
刪除前  sessions=1 events=14  free pages=0   沛原科技=6  會員中心的登入與權限=4
刪除後  sessions=0 events=0   free pages=18  沛原科技=6  會員中心的登入與權限=4
```

用 SQL 查，一筆都沒有
用位元組看，6 處「沛原科技」原封不動

SQLite 刪資料只是把那些 page 標成「可以重用」，在被新資料蓋掉之前，內容都還在檔案裡
18 個空出來的 page，就是昨天那三輪對話

**secure_delete**

SQLite 有一個 `PRAGMA secure_delete`，打開之後，刪除時會把內容寫成 0
ADK 自己已經在 connect 的時候設了 `foreign_keys=ON`（events 靠這個跟著 session 一起刪），我照樣加一個

```python
from sqlalchemy import event

def _secure_delete(dbapi_connection, _record) -> None:
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA secure_delete=ON")
    cur.close()

event.listen(svc.db_engine.sync_engine, "connect", _secure_delete)
```

同一份複本，再刪一次

```text
刪除後  sessions=0 events=0   free pages=18  沛原科技=0  會員中心的登入與權限=0
```

這次真的沒了
檔案大小一樣是 122,880 bytes，內容是寫成 0，不是把檔案縮小；要縮小得另外跑 `VACUUM`，對隱私來說不需要

這個也寫成測試了，而且確認過：把 `secure_delete` 關掉，這個測試會失敗
不然很容易寫出一個「搜中文、永遠通過」的測試

**還沒處理的**

SQLite 預設的 rollback journal，在刪除的那個交易裡會先把原本的 page 寫進 `sessions.db-journal`，交易結束再把這個檔案刪掉
檔案被刪掉之後，磁碟上那些位元組在被覆蓋之前還在
這已經是檔案系統層級的事，我沒有驗證，先記下來；Day 19 上雲端改用受管的 Sessions，這段就變成平台的責任

## 第三個問題：放多久

使用者不一定會記得按刪除
沒刪的 session 要有期限

```python
async def purge_expired(self, ttl_hours: float | None = None) -> int:
    ttl = get_settings().session_ttl_hours if ttl_hours is None else ttl_hours
    cutoff = time.time() - ttl * 3600
    listed = await self._sessions.list_sessions(app_name=APP_NAME)
    expired = [s for s in listed.sessions if s.last_update_time < cutoff]
    for s in expired:
        await self._sessions.delete_session(...)
    return len(expired)
```

預設 24 小時，從 session 最後一次有動作開始算，`SESSION_TTL_HOURS` 可以調
一次分析通常一個晚上就做完了，隔天回來想再改計畫，24 小時也還夠

什麼時候清？沒有排程器，所以兩個時間點

- 服務啟動的時候清一次，不然如果都沒人來，就永遠不會清
- 每次有人開新 session 的時候順便清

量小的時候夠用，Day 19 上雲端之後要換成排程

實測一下，昨天那個 session 現在放了 19.8 小時，24 小時還沒到，啟動時沒被清
把期限改成 12 小時再啟動一次

```text
[before]                 sessions=1 events=14 沛原科技=6
[after startup, TTL=12h] sessions=0 events=0  沛原科技=0
```

到期就清掉，而且一樣不留在檔案裡

## 順便修的：eval 也會留下履歷

`evals/injection.py` 是 Day 18 要用的注入測試，會拿一批埋了攻擊字串的虛構履歷去開 session
它跑完會刪，但 session id 是固定的 `inject-0-0`
昨天把預設改成 SQLite 之後，只要跑到一半出錯，攻擊用的履歷就會留在正式的 `sessions.db` 裡，下次再跑還會撞到同一個 id

測試用的東西不該寫進正式資料庫，改成用記憶體版

```python
session = AgentSession(session_service=make_session_service(""))
```

## 實際打一次

最後全部接起來，用昨天的 `sessions.db` 複本啟動服務，打一次真的模型

```text
start               200  token len 43
owner send          200  llm_calls 1  total_tokens 3,669  17.5 秒
stranger send       404  找不到這個 session，可能已過期或被刪除
no header send      422
stranger delete     404
owner delete        204
owner delete again  404
token in file:      False
```

資料庫在每一步的樣子

```text
[啟動後]   sessions=1 users=['demo-user']                        沛原科技=6
[聊一輪後] sessions=2 users=['anon-3673c44e...', 'demo-user']    沛原科技=10
[刪除後]   sessions=1 users=['demo-user']                        沛原科技=6
```

新 session 的 user 是 `anon-` 加雜湊，不是任何人自己填的名字
刪掉之後，多出來的 4 處「沛原科技」歸零，剩下的 6 處是昨天那個還沒過期的 session

**又沒驗證了**

順便看了一下這輪 agent 的行為：`tool_calls` 是空的，1 次模型呼叫就回答了
昨天同樣的輸入、同樣的 instruction，它把 14 句一次送去驗證
Day 15 記下來的事又出現一次：要不要先驗證，現在還是看它心情
回覆第一句是「陳柏宇您好」，名字也是直接從履歷拿的，這個倒是沒問題

測試從 47 個變成 53 個，全部不打模型

版本：google-adk 2.8.0、google-genai 2.22.0、SQLAlchemy 2.1.1、aiosqlite 0.22.1、gemini-2.5-flash

## 明天

今天處理的是「別人拿不到這份履歷」
明天反過來：如果履歷本身就是攻擊呢？
在虛構履歷裡寫「忽略以上規則」，看 agent 會不會照做、工具的參數會不會被污染
Day 14、15 那個把自己的 instruction 當成可疑文字檢舉的問題，也一起處理

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
