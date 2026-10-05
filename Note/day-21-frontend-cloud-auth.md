---
day: 21
chapter: 5
chapter_title: 部署到平台，觀察真實行為
title: 串起網頁與雲端 Agent：身分驗證、存取控制與結果呈現
date: 2026-10-05
status: writing
---

# Day 21｜串起網頁與雲端 Agent：身分驗證、存取控制與結果呈現

> Recap: 昨天的結論是「門口要自己顧」，agent 留在 Agent Runtime，前面放我們自己的 FastAPI

到昨天為止，雲端的 agent 只有腳本打得到
網頁還是只認識路徑 A 的 `/analyze`，Day 14 之後做的對話、Day 17 的憑證、Day 18 的 guard，畫面上一個都看不到

今天要把這條線接起來

```text
瀏覽器 ──X-Session-Token──▶ FastAPI ──user_id=anon-<雜湊>──▶ Agent Runtime
```

## 後端：換一個實作，端點不動

Day 17 的端點長這樣，今天一行都不改

```text
POST   /agent/sessions                     開對話，回 session_id 跟 token
POST   /agent/sessions/{id}/messages       送訊息，要帶 X-Session-Token
DELETE /agent/sessions/{id}                刪除，要帶 X-Session-Token
```

改的是後面接的東西
新寫一個 `RemoteAgentSession`，介面跟本機的 `AgentSession` 一樣，裡面改打 Agent Runtime

```python
_agent = RemoteAgentSession() if get_settings().agent_backend == "runtime" else AgentSession()
```

`.env` 設 `AGENT_BACKEND=runtime` 就打雲端，不設就是本機的 ADK + SQLite
前端完全不知道後面是哪一個

## 存取控制：Agent Runtime 認 user_id，但相信你給的 user_id

Day 17 在 SQLite 上測過「換一個 user 拿不到」，換成雲端要再測一次
不打模型，只開 session、拿、刪

```text
alice 建 session
bob 拿 alice 的 session      ClientError: 400 INVALID_ARGUMENT ... Reasoning Engine Execution failed.
bob 列出自己的 session       {'sessions': []}
bob 刪 alice 的 session      ClientError: 400 INVALID_ARGUMENT ...
alice 拿自己的 session       OK，state 還在
```

Agent Runtime 有照 user_id 隔開，bob 拿不到也刪不掉
兩個要注意的地方

- 拿不到回的是 400，不是 404，而且訊息是很籠統的「執行失敗」，要自己轉成「找不到」
- 隔離的前提是 user_id 是對的。user_id 是呼叫端給的，誰呼叫、填什麼，它都相信

所以 user_id 絕對不能讓瀏覽器自己填
這裡沿用 Day 17 的做法：開對話時發一個隨機 token，user_id 是 token 的雜湊，資料庫跟 Agent Runtime 都只看得到雜湊

```python
owner = owner_of(x_session_token)          # "anon-" + sha256(token)[:32]
if not await _agent.exists(owner, session_id):
    raise _NOT_FOUND
```

## 保留期限：不設的話放一年

Day 17 在本機做了 24 小時自動清除
雲端的 session 平台在管，翻 ADK 原始碼，`create_session` 可以帶 `ttl`

```python
# E.g. set ttl='7200s' to set the session time-to-live
```

那不帶的話是多久？SDK 回傳的 session 裡沒有到期時間，只好直接打 REST API 看原始資料

```text
ttl=None:    createTime=2026-10-05T11:09:28Z  expireTime=2027-10-05T11:09:28Z
ttl=86400s:  createTime=2026-10-05T11:09:28Z  expireTime=2026-10-06T11:09:28Z
```

**不設的話，履歷在雲端放一年**
SDK 不給你看到期時間，不去查根本不會知道

本來想測試時設短一點，給 `ttl="3600s"`

```text
Field: session.ttl; Message: `ttl` must be at least 24 hours.
```

最短就是 24 小時，跟本機設的一樣，剛好
但有一點不一樣：本機是從「最後一次動作」開始算，雲端是建立時就決定了到期時間，聊天聊到一半不會延長
這個差別我沒辦法在一天內驗證有沒有例外，先照原始資料寫

## 錯誤訊息裡有整份履歷

上面那個 ttl 太短的錯誤，完整的訊息後面還有一段

```text
Request Data: {'state': {'resume_text': '陳柏宇\n後端工程師 / 1 年經驗\nEmail: boyu.chen@example.invalid\n電話: 0900-000-001 ...
```

錯誤訊息把整個請求原樣附上，包括 state 裡的履歷全文、email、電話
我上午剛寫好的錯誤處理，是把雲端的錯誤訊息原樣放進 HTTP 回應的 `detail`，等於會把履歷送回前端；如果沒接住，就變成 500，traceback 會印在伺服器的 log 裡

改成所有雲端的錯誤都先過一次 `clean_error`

```python
def clean_error(msg: str) -> str:
    msg = str(msg)
    cuts = [i for i in (msg.find("Request Data"), msg.find("resume_text")) if i != -1]
    if cuts:
        msg = msg[: min(cuts)] + "…（後面是請求內容，已移除）"
    return msg[:300]
```

再用 `raise AgentError(...) from None` 丟出去，`from None` 是為了不把那個帶著履歷的原始例外接在後面
Day 23 要做 log，這件事到時候還會再碰到

## 錯誤跟逾時要分開講

Day 19 學到，雲端出錯時不會丟例外，而是送一個帶 `error_code` 的 event；Day 20 量到冷啟動要一分鐘
所以「沒有回覆」至少有三種原因，前端要講得出差別

| 狀況 | 後端回 | 前端顯示 |
| --- | --- | --- |
| session 不在了（過期、刪了、不是你的） | 404 | 「這次對話已經不在了」，回到可以重新開始的狀態 |
| 等超過 180 秒 | 504 | 黃色提醒：雲端閒置後第一次可能要一分鐘，可以再送一次 |
| agent 出錯（模型 404、配額…） | 502 | 紅色錯誤，附上清理過的原因 |

180 秒是這樣算的：冷啟動 66 秒（Day 20），加上第一輪可能叫 9 次工具（Day 19，24 秒），再留一點
前端的逾時設 200 秒，比後端長一點，讓後端先回 504 說清楚原因，不要前端自己先放棄

前端原本的 `request()` 把所有 fetch 失敗都當成「連線失敗」，前端自己設的逾時也會被說成連不上，這個也分開了

## 前端：對話模式

左欄加了第 4 張卡片

- 「用上面的履歷開始對話」：用左邊已經貼好、確認過的履歷開 session
- 職缺有填的話，第一句會幫你帶好「我想應徵下面這個職缺……」
- 送出後顯示已等待幾秒，提醒第一句可能要一分鐘
- 「刪除這次的資料」：確認之後打 DELETE

**token 不存 localStorage**

token 只放在 JavaScript 的一個變數裡
存 localStorage 的話，重新整理還回得來，但同一台電腦的下一個人也回得來
履歷是高敏感資料，我選擇關掉分頁就拿不回來，畫面上也直接寫出來
「重新開始」的時候，會先把舊的那份刪掉，不要讓它在雲端等 24 小時

**guard 的結果要看得到**

Day 18 的 `unverified_quotes`，在畫面上做兩件事

- 回覆裡那幾句「」引用直接標黃，滑鼠移上去顯示「履歷裡找不到這句」
- 回覆下面列出來：「有 N 句引用在履歷裡找不到，不要直接採用」

另外加了一句說明：有些可能是 agent 給的改寫建議，不是在說履歷寫了這句
Day 18 看過，guard 標出來的有不少是改寫建議，不講清楚，使用者會以為整個回覆都不能信

被呼叫上限或洩漏擋下來的（`stopped`），顯示成黃色的「這一輪沒有回覆」，不是空白

## 實際打一次：計畫不見了

uvicorn 用 `AGENT_BACKEND=runtime` 跑起來，照前端的順序打一次

```text
start               200   2.5 秒
round1              200  17.5 秒  tools=[]  4,374 tokens
round2              200  26.0 秒  tools=['lookup_resources', 'validate_learning_plan']  20,003 tokens
stranger send       404
stranger delete     404
owner delete        204
send after delete   404
```

存取控制都對，但第 2 輪的回覆是這樣

> 很棒！你的學習計畫已經通過檢核，沒有發現任何衝突或問題。請參考這份學習計畫，補強你的技能。

「請參考這份學習計畫」，但回覆裡沒有計畫

**文字跟工具呼叫寫在同一則**

Day 16 看過一件事：模型會在呼叫工具的同一則回應裡先講一段話
這次它應該是把整份計畫寫在呼叫 `validate_learning_plan` 的那則回應裡，驗證通過之後，最後一則只剩「已通過檢核」

而本機的 runner 跟今天寫的 `RemoteAgentSession`，都只拿「最後一則純文字的回應」當回覆
前面那段，使用者永遠看不到

同樣的請求再跑一次，這次計畫就寫在最後一則，沒事，所以這是看機率的
不能賭機率，改成一輪裡所有要給人看的文字都接起來

```python
turn.text = f"{turn.text}\n\n{text}" if turn.text else text
```

**guard 也漏看了這段**

查這個問題時順便發現：Day 18 的 guard 在 Day 19 搬進 callback 的時候，寫的是「有工具呼叫就跳過」

```python
if any(p.function_call for p in content.parts):
    return None
```

也就是說，跟工具呼叫寫在一起的文字，guard 從來沒看過
以前沒差，因為那段文字也不會顯示；今天改成要顯示，就變成洩漏可以從這裡溜出去

改成：有工具呼叫的回應也檢查文字，有洩漏就只拿掉文字，工具呼叫留著，不然 agent 的流程會斷掉
這個改在 agent 的 callback 裡，所以要重新部署，`--update` 跑了 2 分 42 秒

改完再打一次

```text
round1  200  17.0 秒  tools=[]  4,276 tokens
round2  200  29.0 秒  tools=['lookup_resources', 'validate_learning_plan', 'validate_learning_plan']  24,248 tokens
```

第 2 輪的回覆開頭變成

> 您好，謝謝您提供的資訊！既然 SQL 有接觸過……不過，為了更精確地為您規劃 SQL 的學習內容，想請您多補充一點……

這段是它在呼叫工具的同時寫的，以前會被丟掉，現在看得到了

**第 1 輪又沒驗證**

兩次的第 1 輪都是 `tools=[]`，一次 `verify_evidence` 都沒叫
guard 標出來 6 到 8 句，大部分是 Day 11 就看過的「技能: Git」這種履歷裡沒有的寫法
還有一句是職缺的條件

```text
1 至 3 年後端開發經驗，或具備可展示的完整專案作品
```

職缺是使用者貼的，照理說算有來源；但職缺原文是「1 至 3 年後端開發經驗（含實習年資），或具備……」，模型把中間的括號拿掉了
不是一字不差，所以被標出來，這是對的

## 還沒做的

- FastAPI 還跑在我的電腦上，用我自己的 Google 帳號去打 Agent Runtime
- 有專案權限的人，可以繞過 FastAPI 直接打 Agent Runtime，自己填 user_id。門口要真的有用，得讓 Agent Runtime 只接受 FastAPI 那個身分的呼叫；Day 19、20 看過，現成的角色都太大，要自己做 custom role
- 我沒有在瀏覽器裡實際點過一次：JavaScript 有過語法檢查，後端的流程照前端的順序用程式打過，但畫面上標黃、按鈕狀態這些，要自己開起來看

測試從 71 個變成 83 個，全部不打模型、不連雲端
雲端回傳的 event 格式、400 不是 404、帶著履歷的錯誤訊息，都照今天實際看到的寫成測試

版本：google-adk 2.8.0、google-genai 2.22.0、google-cloud-aiplatform 2.1.0、gemini-2.5-flash

## 明天

今天好幾個問題，都是把一個個 event 印出來才看懂的：計畫寫在哪一則、哪一則有工具呼叫、錯誤藏在哪裡
明天用 Cloud Trace 看一次請求裡到底發生了什麼：呼叫了幾次模型、每個工具花多久、時間都花在哪

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
