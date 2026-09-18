---
day: 15
chapter: 4
chapter_title: 讓 Agent 有狀態，也有界線
title: 工具不是越多越好：設計查詢資源與驗證計畫的 Tool
date: 2026-09-29
status: draft
---

# Day 15｜工具不是越多越好：設計查詢資源與驗證計畫的 Tool

> **今天要做**：把 Day 12 的驗證邏輯和 Day 13 的資源查詢包成 typed tool，定義執行限制。重點是工具的邊界怎麼劃，不是工具有幾個。
>
> **今天的產出物**：（這天結束時 repo 裡多了什麼檔案／端點／資料）

## 前情提要

（一兩句接上昨天。第一天寫動機。）

## 這篇要解決的問題

## 怎麼做的

## 卡住的地方

（沒卡住就刪掉這段。卡住就老實寫排查過程 —— 文章不綁當天技術動作的成功。）

## 今天的結論

## 明天預告

## 實測資料（2026-09-17 蒐集，寫作用素材）

### SDK 層的 AFC 與「工具邊界」的第一個決策點

google-genai 2.22.0 呼叫 `models.generate_content` 時，即使**完全沒有傳 tool**，
也會印出這行警告：

> Direct use of automatic function calling (AFC) in Models.generate_content is not
> recommended. Instead, we recommend to use AFC in Chat.send_message.

原因在 `models.py` 的 `should_disable_afc()`：`if not config: return False`，
註解寫著 `Default to enable AFC if not specified.` —— **預設開啟 AFC**，與有無 tool 無關。
沒給 config 就會走進 AFC 分支並印警告（用 `Models._logged_afc_warning` 旗標，每個 process 只印一次）。

關掉的方式，實測有效且回應內容不變：

```python
types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
)
```

**AFC 是什麼**：把 Python 函式當 tool 傳進去後，SDK 自動執行它、把結果塞回去、再問模型一次，
整個迴圈不用自己寫。官方建議改用 `Chat.send_message`，因為 `generate_content` 無狀態，
AFC 跑多輪時中間的往返不會保留。

**本專案的選擇與理由**（這才是這篇的論點）：不使用 SDK 的 AFC，自己接管工具呼叫。
- Day 22 要用 Trace 看清楚一次請求裡有哪些工具呼叫、各花多久 —— AFC 把迴圈藏起來了。
- Day 24 要做有上限的重試與停止條件 —— 同理。
- 走 ADK 之後工具呼叫由 ADK 管理，不是這層 AFC。

可寫的角度：「工具的邊界」不只是劃在 tool 的參數上，也劃在「誰來驅動這個迴圈」。

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
