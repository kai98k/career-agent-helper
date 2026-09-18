---
day: 03
chapter: 1
chapter_title: 從想法到第一個可操作版本
title: 從零到第一次呼叫：環境建置排查紀錄
date: 2026-09-17
status: writing
---

# Day 03｜從零到第一次呼叫：環境建置排查紀錄

> recap: 昨天簡單介紹了模型、SDK、ADK 與 Runtime 的四層關係，今天把最底下兩層，模型和 Gen AI SDK 實際跑一次看看

今天的目標很單純：從一個空的 Google 帳號，走到程式印出 Gemini 的回應。

原本以為是一篇簡單的安裝教學，結果五個步驟，五個都砸到自己腳
所以這篇比較像是排查紀錄

---

## 開專案、綁帳單、開 API
​
​
GCP Console 跟 gcloud 指令都可以都做得到
​
以 gcloud 來說:
​
```bash
# 1. 建專案。PROJECT_ID 必須全域唯一，--set-as-default 讓 gcloud 直接切過去
gcloud projects create career-agent-helper-508911 \
  --name="career-agent-helper" --set-as-default
​
# 2. 綁帳單帳戶。沒綁的話 API 呼叫會直接被拒
gcloud billing accounts list          # 先抄下 ACCOUNT_ID
gcloud billing projects link career-agent-helper-508911 \
  --billing-account=0X0X0X-0X0X0X-0X0X0X
​
# 3. 開 API
gcloud services enable aiplatform.googleapis.com \
  --project=career-agent-helper-508911
```
​
走 Console 的話：
1. 建專案在右上角專案選單的「新增專案」
2. 開 API 在 **APIs & Services → Library**
3. 搜尋 `Agent Platform API`
​
![https://ithelp.ithome.com.tw/upload/images/20260917/20184275nvvOcj1KDG.png](https://ithelp.ithome.com.tw/upload/images/20260917/20184275nvvOcj1KDG.png)
​

### 我以為 API 開過了

我不小心建了兩個同名GCP專案，把 gcloud 切過去，跑測試程式噴錯
第一個反應是: API 應該有開啊?

```bash
gcloud services list --enabled --filter="config.name:aiplatform"
# aiplatform.googleapis.com
```

有耶! 那為什麼不能用？

**因為那是在舊專案上開的。** API 的啟用狀態綁在單一專案，不會因為同一個帳號或同樣的名稱就繼承過去。

而我查半天沒發現，是因為這兩個專案的**顯示名稱完全一樣**。GCP 的專案 ID 必須全域唯一，名稱被佔用時 Console 會自動補一串數字，於是我有了：

| 顯示名稱 | 專案 ID |
| --- | --- |
| career-agent-helper | `career-agent-helper` |
| career-agent-helper | `career-agent-helper-508911` |

教訓：**所有 gcloud 指令都明寫 `--project`**
省略它等於把「這個操作落在哪裡」交給當下看不見的 config 狀態決定。

動手前先確認自己站在哪：

```bash
gcloud config get-value project
```

---

## ADC：為什麼不用 API key

最簡單的作法可以去 AI Studio 申請一把 gemini API key 塞進程式碼

可參閱: 
https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/sdks/overview?hl=zh-tw

但 API key 蠻容易碰到以下:

1. 它得依賴程式碼或環境變數，然後就有機會被 commit 進 git
2. 它不區分身分，事後查不出是誰用的

ADC（Application Default Credentials）走另一條路：

```bash
gcloud auth application-default login
```

這行會開瀏覽器做 OAuth，把憑證寫到**使用者層級**的位置
（Windows 在 `%APPDATA%\gcloud\`）
跟在哪個資料夾、哪個專案完全無關，所以只要做一次，之後換專案不用重登

但真正讓我選它的理由不是安全，是**連貫性** !

後面要把 agent 部署到雲端，那時候執行的不是我，是一個 service account
ADC 的設計是：本機找你的使用者憑證，雲端找附加在服務上的 service account


### 那 IAM 呢 ?

本機開發時我們不太會遇到權限問題，
因為 ADC 拿的是自己的 Google 帳號，
而我們自己通常是這個專案的 Owner，什麼都能做!

但雲端那邊的 service account 預設權限很窄!
所以 **IAM 的問題現在先不處理，先透過 Owner 來 cover** 
實際要配哪些角色、怎麼給最小權限，留到部署那天再處理

### 怎麼判斷 ADC 有沒有生效

看錯誤碼：

- **401 / 403** → 身分問題，ADC 沒過
- **404** → 認證已經過了、請求真的打到 API 了，是你要的東西不存在

---

## Python 環境與套件

```bash
python3.12 -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
```

今天只會用到 `google-genai`，但我把後面會用到的一起裝，因為版本衝突要撞就今天撞，不要第十幾天才撞：

```bash
pip install "google-genai"
pip install "google-cloud-aiplatform[agent_engines,adk]>=1.112"
pip install "google-adk>=2.0"
pip install "python-dotenv"
```

實際解出來的版本：

| 套件 | 版本 |
| --- | --- |
| Python | 3.12.10 |
| google-genai | 2.22.0 |
| google-adk | 2.8.0 |
| google-cloud-aiplatform | **2.1.0** |

### .env 設定

```bash
GOOGLE_CLOUD_PROJECT=career-agent-helper-508911
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True

# 模型
GEMINI_MODEL=gemini-2.5-flash
```

`.env` 記得加進 `.gitignore`。載入用 python-dotenv：

```python
from dotenv import load_dotenv
load_dotenv()
```

（`GOOGLE_CLOUD_LOCATION` 為什麼是 `global` 而不是 `asia-east1`，就是下一節的故事。）

---


### `USE_VERTEXAI` 還是 `USE_ENTERPRISE`？

我原本寫 `GOOGLE_GENAI_USE_VERTEXAI`，但官方文件現在用 `GOOGLE_GENAI_USE_ENTERPRISE`。兩個看起來都合理，到底該用哪個？

翻 SDK 原始碼（google-genai 2.22.0，`_api_client.py`）：

```python
env_enterprise_str = os.environ.get('GOOGLE_GENAI_USE_ENTERPRISE', None)
env_vertexai_str = os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', None)
# ...
if env_enterprise is not None:
    self.vertexai = env_enterprise
elif env_vertexai is not None:
    self.vertexai = env_vertexai
```

兩個都讀，新名優先。實測：

| 設定 | 結果 |
| --- | --- |
| 只設 `VERTEXAI=True` | 生效 |
| 只設 `ENTERPRISE=True` | 生效 |
| 兩個值衝突 | `ENTERPRISE` 勝出，並發出警告 |
| 值寫成 `yes` | 不認，判成 False |


## `asia-east1` 沒有任何 Gemini 模型

這是今天最大的意外。

我原本的規劃寫著「region 設 `asia-east1`」，理由很單純：機房在彰化，離台灣最近，延遲最低。

結果第一次呼叫就拿到 404：

Publisher model projects/.../locations/asia-east1/publishers/google/models/gemini-2.5-flash
was not found or your project does not have access to it.



第一個想法是模型名稱寫錯。換了 `gemini-2.5-pro`、`gemini-2.0-flash`，全部 404。

於是我寫了個小腳本，拿模型去各區域各打一次。`max_output_tokens=1` 是把成本壓到趨近於零：

```python
from google import genai
from google.genai import types, errors

REGIONS = ["global", "asia-east1", "asia-east2", "asia-northeast1",
           "asia-northeast3", "asia-southeast1", "asia-south1", "us-central1"]
MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]

cfg = types.GenerateContentConfig(max_output_tokens=1)

for loc in REGIONS:
    row = []
    for model in MODELS:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=loc)
        try:
            client.models.generate_content(model=model, contents="hi", config=cfg)
            row.append(f"{model}=OK")
        except errors.ClientError as e:
            row.append(f"{model}={e.code}")
    print(f"{loc:18}", "  ".join(row))
```

拿到結果：

| Region | 2.5-flash | 2.5-pro |
| --- | --- | --- |
| `global` | OK | OK |
| `asia-east1`（彰化） | 404 | 404 |
| `asia-east2`（香港） | 404 | 404 |
| `asia-northeast1`（東京） | OK | OK |
| `asia-northeast3`（首爾） | 429 配額 | 404 |
| `asia-southeast1`（新加坡） | OK | 404 |
| `asia-south1`（孟買） | OK | 404 |
| `us-central1`（愛荷華） | OK | OK |

`asia-east1` 一個都沒有。不是暫時性故障，是這個區域就是沒有供應 Gemini publisher 模型

後來找到官方的模型端點區域表，確認 `asia-east1 台灣` 真的沒有列出任何 Gemini 模型：

https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations?hl=zh-tw#google-models

因為我一開始查錯文件，查到這份「機器學習服務的可用區域」
在那份表裡，`asia-east1` 列著支援 Gemini Enterprise Agent Platform、Agent Platform Pipelines、Model Registry 等等

問題在於那份表講的是**平台功能的可用性**，不是**publisher 模型的供應**

### 為什麼選 global

候選有兩個：`asia-northeast1`（東京）和 `global`。

- `asia-northeast1`的優點是區域固定、延遲可預測
- `global` 的優點是可用性最高、配額壓力最小，官方文件也明說全域端點能降低 `429` 資源耗盡錯誤

---

## 成功：第一次呼叫

環境變數設好，換成 `global`，重跑：

```python
import os

from dotenv import load_dotenv
from google import genai
from google.genai.types import HttpOptions

load_dotenv()

client = genai.Client(http_options=HttpOptions(api_version="v1"))

response = client.models.generate_content(
    model=os.environ["GEMINI_MODEL"],
    contents="AI怎麼運作的?。",
)
print(response.text)
```

輸出：

![https://ithelp.ithome.com.tw/upload/images/20260917/20184275zyQarhXr75.png](https://ithelp.ithome.com.tw/upload/images/20260917/20184275zyQarhXr75.png)

## 明天預告

今天的呼叫還停在一支腳本裡。明天把它變成一個服務：建立 FastAPI 專案，把履歷分析包成一個端點，有輸入有輸出

順便把帳算清楚，這幾次呼叫到底花了多少、錢是花在哪一段 

---

<!-- 待補
- [ ]〈成功：第一次呼叫〉：貼實際輸出 + 寫那一兩句觀察（這是全篇的鉤子，別省）
- [ ] 截圖：啟用 API 頁面
- [ ] 截圖：Console 專案選單（兩個同名專案並列）
- [ ] 截圖：成功呼叫的終端機畫面
-->

<!-- 發文前檢查
- [ ] 內文 300 字以上，且切題
- [ ] 履歷資料全部虛構，沒有用到任何真實履歷（含自己的）
- [ ] 程式碼片段可執行，並標示套件版本
- [ ] 截圖已去識別化，沒有露出 project id / 帳號 / 金鑰
- [ ] 有連回前一天、預告下一天
-->