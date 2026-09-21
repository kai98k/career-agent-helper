---
day: 07
chapter: 2
chapter_title: 讓履歷分析有依據
title: 讓模型輸出可被程式使用：履歷與職缺的結構化解析
date: 2026-09-21
status: writing
---

# Day 07｜讓模型輸出可被程式使用：履歷與職缺的結構化解析

> Recap: 昨天把輸入固定了，今天換輸出

Day 04 的回應長這樣

```python
class AnalyzeResponse(BaseModel):
    model: str
    prompt: str
    analysis: str        # 一整段 Markdown
    usage: Usage
    elapsed_ms: int
```

拿[四年後端那份](https://github.com/kai98k/career-agent-helper/blob/main/data/resumes/sample-backend-4y.txt)實際打一次，可以拿到以下

```json
{
  "model": "gemini-2.5-flash",
  "prompt": "analyze_v1",
  "analysis": "根據您提供的履歷內容，身為職涯顧問，以下提出三點可以改進的地方：\n\n1.  **工作經歷中缺乏具體成就與量化成果的呈現：**\n    目前的「工作經歷」描述……\n\n2.  **「技能」部分的深度與廣度可進一步說明：**\n    ……\n\n3.  **「自我介紹」與「其他」的軟性技能缺乏實例佐證：**\n    ……",
  "usage": { "prompt_tokens": 525, "thought_tokens": 2126, "output_tokens": 454, "total_tokens": 3105 },
  "elapsed_ms": 13900
}
```

然後分析的內容全擠在 `analysis` 這一個字串裡，其他欄位只是 metadata

再來我們要用程式解析回應
所以今天先不分析，就只先做一件事：把履歷跟職缺拆成欄位

## 兩層保證

Gemini 可以直接吃 pydantic 的 class 當 schema

```python
cfg = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=schema,
)
```


但模型說它回的會是 JSON，不代表欄位都是對的
所以拿回來之後再用 pydantic 驗一次，如果驗不過就直接報錯

```python
data = schema.model_validate(json.loads(resp.text))
```

## 欄位怎麼定

每個欄位主要都在驗證這個 value 能不能對回原文

| 欄位 | 怎麼做 | 為什麼 |
| --- | --- | --- |
| `period` | 原文照抄，不轉日期 | 轉成日期物件就對不回原文了 |
| `years_experience` | 履歷有寫就填 | 因為推算出來的數字會沒有原文能對照 |
| `bullets` | 逐條照抄 | 這層只負責拆成列項 |
| `missing_fields` | 沒提到的欄位放這裡 | 就算是沒有寫到的也要記錄 |

另外每個 schema 掛一個 `schema_version = "v1"`，Day 26 比較新舊 prompt 時要用

## 卡住的地方

拿昨天的實習生履歷跑第一次，回來的是

```json
"schema_version": "null"
```

字串的 `"null"`，pydantic 照收，因為它只檢查是不是字串

原因是 `schema_version` 也被送進 `response_schema`，版本號變成模型在填
這個值應該由程式決定，所以改成模型看不到、回了也會被蓋掉

```python
SchemaVersion = Annotated[SkipJsonSchema[str], BeforeValidator(lambda _: SCHEMA_VERSION)]
```

## 實測

改完再跑兩份

[四年後端那份](https://github.com/kai98k/career-agent-helper/blob/main/data/resumes/sample-backend-4y.txt)（`vague`），履歷第二行寫「4 年經驗」，所以 `years_experience` 填 `4.0`
bullets 原文照抄，「負責公司產品的系統開發與維護」一個字都沒改，沒有腦補

[實習生那份](https://github.com/kai98k/career-agent-helper/blob/main/data/resumes/sample-student-intern.txt)：

```json
{
  "schema_version": "v1",
  "years_experience": null,
  "missing_fields": ["years_experience"]
}
```

年資沒寫，也沒自己算，也記進了 `missing_fields`
但同一份履歷，第一次跑的 `missing_fields` 是空的

同樣的輸入，兩次結果不一樣
這就是為什麼昨天要先有固定的資料集(Dataset)，只跑一次看不出來

另外第一次呼叫還吃了一個 429，`global` 的共用額度暫時滿了，重跑就過，之後再來提這個

版本：google-genai 2.22.0、pydantic 2.13.5、gemini-2.5-flash

## 明天

現在輸入還是貼文字
但大家手上的履歷都是 PDF，明天處理上傳、解析失敗，以及讓使用者確認解析出來的內容

---

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->
