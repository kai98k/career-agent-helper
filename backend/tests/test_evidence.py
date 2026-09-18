"""引用驗證的行為測試。

重點在三態的邊界：什麼算照抄、什麼算改過、什麼算沒有。
誤判成本不對稱 —— 把誠實引用判成捏造，會讓使用者不信任系統；
把捏造判成照抄，會讓系統失去存在意義。
"""

from app.services.evidence import Verdict, find, unsupported, verify_all

# 模擬 pypdf 抽出來的樣子：換行、多重空格、縮排都還在
SOURCE = """林可薇
後端工程師 / 4 年經驗

沛原科技    後端工程師    2022/03 - 迄今
- 負責訂單服務的開發與維護，使用 Python 與 FastAPI
- 建置內部部署流程，導入 CI/CD，團隊五人
"""


def test_exact_match_after_whitespace_normalization():
    """模型照抄但把換行壓平了，這仍然是誠實引用。"""
    quote = "負責訂單服務的開發與維護，使用 Python 與 FastAPI"
    c = find(quote, SOURCE)
    assert c.verdict is Verdict.EXACT
    assert c.ok


def test_match_across_line_breaks():
    """跨行的引用，模型會用一個空格接起來。"""
    quote = "後端工程師 2022/03 - 迄今 - 負責訂單服務的開發與維護，使用 Python 與 FastAPI"
    assert find(quote, SOURCE).verdict is Verdict.EXACT


def test_offsets_point_into_the_original_text():
    """位置要能指回原文，不然 UI 標不出來。"""
    quote = "導入 CI/CD，團隊五人"
    c = find(quote, SOURCE)
    assert c.verdict is Verdict.EXACT
    assert SOURCE[c.start : c.end].replace("\n", " ").strip() == quote


def test_fullwidth_and_case_differences_still_match():
    quote = "使用 ｐｙｔｈｏｎ 與 ＦａｓｔＡＰＩ"
    assert find(quote, SOURCE).verdict is Verdict.EXACT


def test_altered_quote_is_flagged_not_accepted():
    """模型多加了「三年」，原文沒有。這是警訊，不是通過。"""
    quote = "負責訂單服務的開發與維護三年，使用 Python 與 FastAPI"
    c = find(quote, SOURCE)
    assert c.verdict is Verdict.ALTERED
    assert not c.ok
    assert c.closest is not None


def test_fabricated_quote_is_not_found():
    """完全捏造的成果，原文一個字都沒有。"""
    quote = "導入 CI/CD 後部署時間縮短 30%，並主導跨部門協作"
    c = find(quote, SOURCE)
    assert c.verdict is Verdict.NOT_FOUND
    assert not c.ok


def test_empty_quote_is_not_found():
    assert find("   ", SOURCE).verdict is Verdict.NOT_FOUND


def test_unsupported_returns_only_problems():
    quotes = [
        "導入 CI/CD，團隊五人",                       # 照抄
        "部署時間縮短 30%",                            # 捏造
        "負責訂單服務的開發與維護三年",                  # 改過
    ]
    assert len(verify_all(quotes, SOURCE)) == 3
    bad = unsupported(quotes, SOURCE)
    assert len(bad) == 2
    assert {c.verdict for c in bad} == {Verdict.NOT_FOUND, Verdict.ALTERED}
