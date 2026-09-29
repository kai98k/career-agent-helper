---
day: 12
chapter: 3
chapter_title: 從分析結果走向學習行動
title: 別讓 AI 憑空排課：產生個人化學習計畫，並用程式檢查時數與先修條件
date: 2026-09-26
status: writing
---

# Day 12｜別讓 AI 憑空排課：產生個人化學習計畫，並用程式檢查時數與先修條件

> Recap: 昨天先問清楚，剩下真正沒證據的才往下走

今天把對照結果變成學習計畫
模型很會排課表，排出來的東西讀起來都很合理
但時數會加錯、先修會顛倒、某一週會排到二十小時，這些都是算得出來的

所以一樣是模型產生、程式檢查

## 程式檢查什麼

```python
def validate(plan: LearningPlan) -> ValidatedPlan:
    """純程式驗證。不呼叫模型，也不該呼叫。"""
```

| 檢查 | 例子 |
| --- | --- |
| 總時數對不對 | 宣稱 20 小時，實際加起來 6 小時 |
| 每週有沒有超過上限 | 使用者說每週 8 小時，第 1 週排了 13 小時 |
| 先修順序 | 「PostgreSQL 調校」排第 1 週，先修「SQL 基礎」排第 3 週 |
| 先修存不存在 | 先修寫了一個計畫裡根本沒有的項目 |
| 資源 id 存不存在 | 模型自己編了一個 `udemy-course-12345` |
| 時數大於 0 | 某一項排了 0 小時 |

同一週也不算先修完成，先修一定要排在更早的週

資源的部分，模型只能從一份本地的清單裡挑 id
清單裡每一筆都有 `verified` 欄位，要人自己打開連結確認過才會設成 `true`
沒核實過的，模型根本看不到

## 卡住的地方：計畫從來沒跑成功過

測試都有過，拿真的履歷跑第一次就炸了

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for Schema
properties.items.items.properties.hours.exclusiveMinimum
  Extra inputs are not permitted
```

原因是 schema 裡這一行

```python
hours: float = Field(gt=0, description="這一項預估要花的時數")
```

`gt=0` 轉成 JSON Schema 會變成 `exclusiveMinimum`
google-genai 的 `Schema` 不認得這個欄位，請求還沒送出去就被擋掉了

測試為什麼沒抓到？
因為計畫的測試全部不打模型，只測 `validate()`，schema 從來沒被送去 SDK 轉過

改法是把 `gt=0` 拿掉，「時數要大於 0」改成 `validate()` 裡的一條規則
另外補一個測試，直接用 SDK 的轉換函式把 schema 轉一次

```python
def test_plan_schema_is_accepted_by_genai():
    from google.genai import _transformers
    _transformers.t_schema(None, LearningPlan)  # 不丟例外就算過
```

拿舊的 `Field(gt=0)` 跑這個測試，會丟 `ValidationError`，確定抓得到

## 第一份計畫

修好之後，一年後端對初階職缺，每週 8 小時

| 週 | 主題 | 時數 |
| --- | --- | --- |
| 1 | SQL基礎語法 (SELECT, FROM, WHERE) | 8 |
| 2 | SQL資料操作與彙總 | 8 |
| 3 | SQL多表查詢與子查詢 | 8 |
| 4 | 資料庫索引與效能優化概念 | 8 |
| 5 | Docker基礎 | 8 |
| 6 | Dockerfile撰寫與Docker Compose | 8 |
| 7 | 小型專案實作：資料庫規劃與建置 | 4 |
| 8 | 小型專案實作：應用程式容器化與CI/CD概念整合 | 4 |

總共 56 小時，**程式檢查 0 個問題**
總時數對、每週沒超過 8 小時、先修順序都對

但這份計畫是錯的

一個寫了一年 Spring Boot 的人，要花四週從 `SELECT` 開始學 SQL
第 7、8 週的專案，理由寫的是「展現自學能力，回應非資訊本科但成功轉職的自學經歷」
可是他就是資工系畢業的

## 問題出在我自己

回頭看餵給計畫的輸入

```python
if m.verdict.value == "not_found":
    lines.append(f"- 缺：{m.requirement}")
```

Day 09 才寫過「沒寫到不等於不會」，結果交給計畫的時候，我自己寫成了「缺」
模型照字面讀，缺就從頭教

然後拿 Day 11 回答過問題的版本再跑一次
SQL 跟 Docker 都有證據了，只剩「非資訊本科」一條
結果是 8 週的 Python 入門，從變數、資料型態開始，最後做一個 CLI 工具放上 GitHub
每一項的理由都是「證明非資訊本科的自學轉職能力」

54 小時，程式檢查一樣 0 個問題

時數加總、先修順序都是對的，但整份計畫一點意義都沒有
程式檢查得了算術，檢查不了這件事該不該學

## 改了三個地方

1. 給計畫的字眼改成「履歷沒有證據（不確定會不會）」
2. prompt 加一條：學歷、是否本科、年資這種背景條件，不是學了就會有，不要排進計畫
3. prompt 再加一條：不需要把週數排滿，要補的少，計畫就短，沒有要補的可以是空的

第 3 條是因為兩份計畫都剛好排滿 8 週，看起來像是在湊

改完用同樣的輸入再跑

| 輸入 | 改之前 | 改之後 |
| --- | --- | --- |
| 沒回答問題（3 條沒證據） | 8 週、56 小時 | 5 項、20 小時 |
| 回答過問題（剩非資訊本科） | 8 週 Python 入門、54 小時 | 空的 |

「非資訊本科」兩次都沒再排進去
沒回答的版本還是從 SQL 基礎開始，但從 32 小時降到 12 小時

這也是 Day 11 要先問的原因，字眼改得再好，模型還是不知道他到底會不會

## 空計畫算不算錯

改完又撞到一個問題：回答過問題的版本，計畫是空的，但程式判定有問題

```text
計畫裡一個項目都沒有
```

這條規則原本是防模型什麼都沒回
現在空計畫變成合理的結果了，但這條規則又不能直接拿掉，Day 14 會看到為什麼

所以改成呼叫的人自己決定

```python
def validate(plan: LearningPlan, *, allow_empty: bool = False) -> ValidatedPlan:
```

固定流程傳 `allow_empty=True`，其他地方維持預設

## 資源是空的

最後，這幾份計畫的 `resource_ids` 全部是空的

資源清單裡 6 筆，`verified` 全部還是 `false`，我還沒一個一個打開確認
所以模型拿到的是「目前沒有已核實的資源，resource_ids 一律留空」，它也照做了

寧可沒有，也不要推一個打不開的連結給正在找工作的人

版本：google-genai 2.22.0、pydantic 2.13.5、gemini-2.5-flash

## 明天

證據、澄清、改寫、計畫都有了，但全部還是 JSON
明天把它們做成一個看得懂的畫面

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
