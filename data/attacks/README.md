# 注入測試素材

這些是刻意埋了攻擊字串的**虛構**履歷，用來測試 prompt injection。

放在 `data/attacks/` 而不是 `data/resumes/`，是為了不讓它們混進正常的評估資料集。

每個檔案的攻擊類型寫在檔名裡。跑 `evals/injection.py` 會逐一送進系統並檢查模型有沒有照做。
