> Recap: 昨天主要在說要做甚麼，今天來講會用到的 Tool !

前陣子在團隊開發時，聽到其他同事說這個 Workflow 要上 Vertex AI，
但是實際去查 Vertex AI 卻跳出 Gemini Enterprise Agent Platform ?

然後再深入搜尋 Gemini Enterprise Agent Platform，
會出現 Vertex AI、Agent Engine、Agent Platform、Agent Runtime、ADK、Gen AI SDK 很多術語跟名詞?

再點進去看了幾篇別人整理的文章之後更混亂了，
像是有的教學說要裝 `google-generativeai`，有的說 `google-genai`，
有的部署到 `Agent Engine`，有的部署到 `Agent Runtime`

原來不單純是我看不懂，更多的是:

>Google 在 Cloud Next 2026 發表 Gemini Enterprise Agent Platform，以 Vertex AI 為基礎打造的新企業級AI代理平臺。Vertex AI 服務及其未來更新都將改由 Agent Platform 交付，而非再以獨立服務形式提供。新平臺會以建構、擴展、治理與最佳化四面向，涵蓋企業級AI代理的完整生命周期。

節錄自 https://www.ithome.com.tw/news/175287

## 先講結論：2026 年 4 月，整個 Vertex AI 被改名了
![https://ithelp.ithome.com.tw/upload/images/20260916/20184275ZhAL4Dwzyf.png](https://ithelp.ithome.com.tw/upload/images/20260916/20184275ZhAL4Dwzyf.png)
2026 年 4 月 22 日，Google 宣布 Gemini Enterprise Agent Platform 作為 Vertex AI 的接替演進，
並在官方 release notes 附上一整張新舊名稱對照表。

挑幾個跟這個系列有關的：

| 舊名稱 | 新名稱 |
|---|---|
| Vertex AI Platform | Agent Platform |
| Vertex AI Studio | Agent Studio |
| Vertex AI API | Agent Platform API |
| Vertex AI Agent Engine | Agent Runtime |
| Vertex AI Agent Engine Sessions | Agent Platform Sessions |
| Vertex AI Agent Engine Memory Bank | Agent Platform Memory Bank |
| Vertex AI Search | Agent Search |
| Vertex AI RAG Engine | RAG Engine |

完整清單在官方 release notes 的 2026/4/22 發布:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes#April_22_2026

**要強調的是，改的是名字，不是服務本體。既有的 ADK 程式照常跑，多數使用者什麼都不用改**

會覺得麻煩的只有一件事，就是網路上的資料有些還在用舊名字
而且你不知道哪些是差不多的或是不同的東西

希望能透過今天來釐清與整理一下

## 四層分工
![https://ithelp.ithome.com.tw/upload/images/20260916/20184275BFALdK7jhv.png](https://ithelp.ithome.com.tw/upload/images/20260916/20184275BFALdK7jhv.png)

把名詞拆開之後，其實只有四層

### 模型（Gemini）

負責推理與生成。這一層就像是決策大腦，也就是「聰不聰明」
使用 Gemini 2.5 Flash 還是 Pro、或是要不要用結構化輸出，都算在這一層

### Gen AI SDK（`google-genai`）

呼叫模型的統一介面。這一層決定「怎麼呼叫」。

需要注意的是舊的 `google-generativeai` 已經棄用
官方支援在 2025 年 11 月 30 日就結束了。所以在網路上有機會看到舊寫法：

```python
import google.generativeai as genai
genai.configure(api_key="...")
model = genai.GenerativeModel("gemini-2.5-pro")
```

現在比較新的寫法是以下：

```python
from google import genai
client = genai.Client()
```

建立一個中央 Client 物件當作入口，憑證與設定統一管理

### ADK（`google-adk`）

Agent 框架。這一層決定「怎麼組裝成 agent」

它提供 agent loop、typed tools、多 agent 組合（循序、平行、迴圈、階層）、session 原語，以及一套評估框架。

而這邊也要注意 ADK Python 已經到 2.0，1.x 到 2.x 有破壞性變更
而網路上有些 ADK 教學是 1.x 寫的
在安裝時需要注意版本

### Agent Runtime

託管執行環境。這一層決定「跑在哪裡」
提供了 sessions、autoscaling、內建 tracing
以及 Cloud console 上的 playground

## 每一層都可以抽掉

這四層不是綁在一起的同捆包

- 不用 ADK 也能呼叫 Gemini，可以直接用 Gen AI SDK 就好，後續會再介紹
- 不用 Agent Runtime 也能跑 ADK，可以在 Cloud Run、GKE 運行
- 不用 Gemini 也能用 ADK，ADK 本身是 model-agnostic 的

## 明天

將環境實際建起來：Google Cloud 專案、ADC、IAM 與預算告警，然後跑通第一支 Gemini 呼叫 !