---
day: 11
chapter: 3
chapter_title: 從分析結果走向學習行動
title: 先問清楚再下結論：設計技能與經驗的澄清流程
date: 2026-09-25
status: writing
---

# Day 11｜先問清楚再下結論：設計技能與經驗的澄清流程

> Recap: 昨天改寫學會用問的，不自己編數字

Day 09 講過，`not_found` 是「履歷沒有證據」，不是「這個人不會」
但到目前為止，固定流程拿到 `not_found` 之後就直接往下走了
沒有人去問他到底會不會

拿[一年後端那份](https://github.com/kai98k/career-agent-helper/blob/main/data/resumes/sample-backend-1y.txt)對[初階後端職缺](https://github.com/kai98k/career-agent-helper/blob/main/data/jobs/sample-job-backend-junior.txt)，有三條 `not_found`

- 能撰寫基本的 SQL 查詢，理解資料表關聯與索引用途
- 接觸過 Docker 或任一 CI/CD 工具
- 有非資訊本科但成功轉職的自學經歷

第一條最明顯
一個寫了一年 Spring Boot、做過會員中心跟報表的人，沒寫過 SQL 的機率很低
只是履歷上剛好沒寫

所以今天在對照跟排計畫中間，多插一步：先問

## 哪些要問，由程式決定

要問什麼，第一步不交給模型
`not_found` 跟 `indirect` 的要求才是候選，這個用程式挑

```python
def candidates(matching: MatchReport) -> list[str]:
    return [
        m.requirement
        for m in matching.matches
        if m.verdict in (MatchVerdict.NOT_FOUND, MatchVerdict.INDIRECT)
    ]
```

模型只負責把候選寫成問題，prompt 裡幾條規則

```text
2. 問題要具體，要從履歷裡已經寫到的經歷切入。
   不要問「你會 SQL 嗎」，要問「你在 XX 專案做報表時，有自己寫 SQL 查詢嗎？」
3. 一個問題只問一件事，使用者要能用一兩句話回答。
4. 如果某項要求是履歷已經寫了相反事實的（例如要求非本科，履歷寫本科），不要問。
```

回來之後程式再檢查一次

- 問題對應的要求不在候選清單裡，直接丟掉
- 最多三題，超過的用程式切掉，不靠模型守規矩

問太多題，使用者就不會回答了

## 回答不改履歷

這是今天想比較久的地方

使用者回答「有，報表的查詢是我自己改的」，這句話要放哪？

直接塞進履歷裡最簡單，但不對
履歷是使用者要交出去的文件，回答只是這次分析的依據
如果混在一起，Day 10 的改寫就可能把使用者口頭說的事，當成履歷上已經寫的事實拿去改寫

所以回答另外附在履歷後面，加一個標頭

```text
【使用者補充：以下是使用者回答澄清問題的內容，不在原履歷中】
關於「能撰寫基本的 SQL 查詢…」：有，報表的查詢是我自己改的…
```

然後重新對照一次
Day 09 的引用驗證本來就會記下引用在原文的位置，所以只要看位置落在哪一段，就知道是履歷寫的還是使用者說的

```python
if chk.start is not None:
    from_answer = boundary is not None and chk.start >= boundary
    m.quote_source = "user_answer" if from_answer else "resume"
```

`boundary` 就是原履歷的長度

## 實際跑一次

第一輪，對照完產生問題
三條 `not_found`，只問了兩題

> 你在沛原科技調整既有報表計算邏輯時，是否有自己撰寫或修改 SQL 查詢語句來實現需求？
>
> 在沛原科技開發或部署服務時，團隊是否有使用 Docker 或 CI/CD 工具？如果有，你主要參與了哪些方面？

「非資訊本科」那條沒問，履歷寫資工系，規則 4 生效
SQL 那題是從履歷裡的「報表」切入，不是空泛地問會不會，這個我滿意

第二題就有點問題，後半句「你主要參與了哪些方面」是第二個問題，違反了一次只問一件事

接著扮演使用者回答

- SQL：有，報表的查詢是我自己改的，會用 JOIN 跟 GROUP BY。索引是請 DBA 幫忙加的，我自己沒加過。
- Docker：公司部署是另一組在管，我沒碰過。Docker 只有在自己電腦跑過 MySQL 的 container。

第二輪，帶著回答重新對照

| 要求 | 第一輪 | 第二輪 | 引用來源 |
| --- | --- | --- | --- |
| SQL 查詢、資料表關聯與索引 | not_found | direct | 使用者補充 |
| Docker 或 CI/CD | not_found | direct | 使用者補充 |
| 非資訊本科轉職 | not_found | not_found | |

`direct` 從 7 條變 9 條
而且畫面上會知道這兩條的證據是「你說的」，不是「履歷寫的」

兩輪各跑了 51.5 秒、49.3 秒，都是 4 次模型呼叫，大約 1.1 萬 tokens

## 還是有問題

**SQL 那條判得太寬**

回答裡明講「索引是請 DBA 加的，我自己沒加過」
但要求寫的是「理解資料表關聯與索引用途」，模型還是整條判 `direct`
一條要求裡面包了三件事，只要證明其中一件，模型就傾向整條算過

**Linux 那條第二輪驗證沒過**

這次模型引用的是「技能: Linux 基本指令」
履歷原文是「【技能】」一行，下一行才是「Java、Spring Boot…Linux 基本指令」
模型把標題跟內容接成一句，還自己加了冒號，程式比對不到，標成驗證沒過

第一輪同一條引用的是「Linux 基本指令」，驗證有過
同樣的輸入，這次換它出錯，所以 Day 09 的驗證不能省

**只問一輪**

固定流程只能問一次
回答之後如果又冒出新的疑問，例如「你說跑過 MySQL container，那 docker compose 有用過嗎」，沒有地方可以再問
要來回問，就需要記得前面問過什麼、答過什麼，這就是 Day 16 Sessions 要處理的

版本：google-genai 2.22.0、pydantic 2.13.5、gemini-2.5-flash

## 明天

問完之後，剩下真正要補的東西才拿去排學習計畫
明天處理計畫，還有為什麼計畫不能只信模型

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
