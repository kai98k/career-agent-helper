---
day: 05
chapter: 1
chapter_title: 從想法到第一個可操作版本
title: 為什麼我沒用 ADK 的 dev UI

date: 2026-09-19
status: writing
---

# 為什麼我沒用 ADK 的 dev UI

> Recap: 昨天把腳本包成 `/analyze`，但要用它還得開 Swagger


Day 02 提過 ADK 是把模型組裝成 agent 的框架
它除了框架本身，還附一個 `adk web` 指令
會起一個本機網頁讓你跟 agent 對話、看它呼叫了哪些工具
照著官方最小範例建了一個空殼，就是一個 `agent.py`、一個 `root_agent`
什麼工具都沒有，純粹讓 `adk web` 有東西可以載入

```bash
adk web app/agent
```


dev UI 當除錯工具
使用者的畫面需要再額外自己做
對於 ADK 來說，今天只是先看它附的畫面

跑完之後 `app/agent/` 底下多了 `.adk/session.db`
是 dev UI 自建的本機 SQLite，存著每次對話

```gitignore
.adk/
```

## 自己刻：一頁 HTML

`web/index.html`，HTML、CSS、JS 寫在一起，沒有 build step。FastAPI 掛成靜態檔：

```python
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
```

**這行一定要放在 `main.py` 最後面。** mount 在 `/` 會接走所有路徑，放前面的話 `/analyze` 會先被靜態檔那層吃掉。


## 明天

明天先做一批虛構履歷跟職缺，之後每改一次 prompt 都拿同一批去跑，看看結果會怎麼樣
