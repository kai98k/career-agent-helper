"""引用驗證：模型說它引用了履歷裡的某句話，這裡負責確認那句話真的存在。

這是程式比對，不是再問一次模型。再問一次模型只是多一個同源的意見，
而這個專案的整個立論就是不要只相信模型的自我宣稱。

為什麼不能直接用 `quote in source`：
pypdf 抽出來的文字帶著 PDF 的換行與多重空格，模型複述時會把它正規化掉。
實測一句 180 字的引用，原樣比對 False，空白正規化後 True —— 模型其實照抄了，
是空白害的。天真比對會把「誠實引用」誤判成「捏造」。
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

# 相似度高於這個值，視為「模型引用了但改了字」，而不是憑空捏造。
# 0.85 是手調的起點，Day 25 建立 rubric 時應該用資料集重新校準。
_NEAR_MISS_THRESHOLD = 0.85

_WS = re.compile(r"\s+")


class Verdict(str, Enum):
    EXACT = "exact"          # 正規化後完全相符，引用可信
    ALTERED = "altered"      # 找得到很接近的原句，但模型改過字 —— 警訊
    NOT_FOUND = "not_found"  # 原文裡沒有這句話


@dataclass(frozen=True)
class EvidenceCheck:
    quote: str
    verdict: Verdict
    similarity: float
    start: int | None = None   # 在「原始」source 中的位置，給 UI 標亮用
    end: int | None = None
    closest: str | None = None  # ALTERED 時，原文裡最接近的那段

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.EXACT


def _normalize(text: str) -> tuple[str, list[int]]:
    """壓平空白並統一全半形，同時回傳每個字元對應回原文的索引。

    索引表是為了讓 UI 能標亮原文。少了它，比對成功也指不出位置。
    """
    out: list[str] = []
    index: list[int] = []
    prev_space = True  # 開頭的空白直接吃掉
    n = len(text)
    i = -1
    while True:
        i += 1
        if i >= n:
            break
        ch = text[i]
        # PDF 常把 end-to-end、ConfigMap-driven 這類詞斷在連字號後換行。
        # 模型複述時會還原成不含換行的樣子，所以這裡只吃掉換行、保留連字號，
        # 否則多出來的空格會讓誠實引用被判成 ALTERED（實測踩過）。
        if ch == "-" and i + 1 < n and text[i + 1] == chr(10):
            out.append("-")
            index.append(i)
            prev_space = False
            while i + 1 < n and text[i + 1].isspace():
                i += 1
            continue
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                index.append(i)
                prev_space = True
            continue
        # NFKC 會把全形英數、全形括號轉成半形，避免同一個字兩種寫法比不到
        norm = unicodedata.normalize("NFKC", ch)
        for c in norm:
            out.append(c.casefold())
            index.append(i)
        prev_space = False
    while out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def find(quote: str, source: str) -> EvidenceCheck:
    """在 source 裡找 quote，回傳判定與原文位置。"""
    q = quote.strip()
    if not q:
        return EvidenceCheck(quote=quote, verdict=Verdict.NOT_FOUND, similarity=0.0)

    n_src, idx = _normalize(source)
    n_q, _ = _normalize(q)
    if not n_q:
        return EvidenceCheck(quote=quote, verdict=Verdict.NOT_FOUND, similarity=0.0)

    pos = n_src.find(n_q)
    if pos != -1:
        start = idx[pos]
        end = idx[pos + len(n_q) - 1] + 1
        return EvidenceCheck(
            quote=quote, verdict=Verdict.EXACT, similarity=1.0, start=start, end=end
        )

    # 找不到完全相符，看看是不是只差幾個字。
    #
    # 不能直接用最長連續片段當相似度：在句子中間插一個詞（模型最常見的動手腳方式）
    # 會把字串切成兩半，最長片段只剩一半左右，誠實引用會被誤判成捏造。
    # 所以先用最長片段定位，再在原文取一個窗口算整體相似度。
    sm = SequenceMatcher(None, n_src, n_q, autojunk=False)
    anchor = sm.find_longest_match(0, len(n_src), 0, len(n_q))
    if not anchor.size:
        return EvidenceCheck(quote=quote, verdict=Verdict.NOT_FOUND, similarity=0.0)

    # 窗口對齊 quote 在 anchor 中的相對位置，前後各留一點餘裕給增刪。
    pad = max(8, len(n_q) // 4)
    lo = max(0, anchor.a - anchor.b - pad)
    hi = min(len(n_src), lo + len(n_q) + 2 * pad)
    window = n_src[lo:hi]
    blocks = [
        b
        for b in SequenceMatcher(None, window, n_q, autojunk=False).get_matching_blocks()
        if b.size
    ]

    # 分母用引用長度而不是 ratio()，因為窗口為了容納增刪多留了 padding，
    # 用 ratio() 會被 padding 稀釋，把只差兩個字的引用打成捏造。
    # 這個分數的意思是：「模型宣稱引用的內容，有多少比例真的照順序出現在原文裡」。
    similarity = sum(b.size for b in blocks) / len(n_q)

    if similarity >= _NEAR_MISS_THRESHOLD and blocks:
        # 回報的範圍收斂到實際對到的部分，不要把 padding 也標亮。
        first, last = blocks[0], blocks[-1]
        start = idx[lo + first.a]
        end = idx[lo + last.a + last.size - 1] + 1
        return EvidenceCheck(
            quote=quote,
            verdict=Verdict.ALTERED,
            similarity=similarity,
            start=start,
            end=end,
            closest=source[start:end],
        )

    return EvidenceCheck(quote=quote, verdict=Verdict.NOT_FOUND, similarity=similarity)


def verify_all(quotes: list[str], source: str) -> list[EvidenceCheck]:
    return [find(q, source) for q in quotes]


def unsupported(quotes: list[str], source: str) -> list[EvidenceCheck]:
    """只回傳有問題的那些，給 agent 的工具當守門員用。"""
    return [c for c in verify_all(quotes, source) if not c.ok]
