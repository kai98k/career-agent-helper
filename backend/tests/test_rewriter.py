"""改寫的程式驗證測試。不打模型，驗的是那兩道檢查會不會漏掉捏造。"""

from app.schemas.rewrite import RewriteItem, RewriteReport
from app.services.rewriter import _numbers, _verify

SOURCE = """沛原科技    後端工程師    2022/03 - 迄今
- 建置內部部署流程，導入 CI/CD，團隊五人
- 負責訂單服務的開發與維護
"""


def _run(original: str, rewritten: str) -> RewriteItem:
    rep = _verify(
        RewriteReport(items=[RewriteItem(original=original, rewritten=rewritten)]),
        SOURCE,
    )
    return rep.items[0]


def test_number_extraction():
    assert _numbers("縮短 30% 並支援 1,200 筆") == ["30%", "1,200"]
    assert _numbers("沒有數字") == []


def test_faithful_rewrite_passes():
    item = _run(
        "建置內部部署流程，導入 CI/CD，團隊五人",
        "主導五人團隊建置內部部署流程並導入 CI/CD",
    )
    assert item.source_verified
    assert item.invented_numbers == []
    assert item.safe


def test_invented_percentage_is_caught():
    """這正是模型實際會做的事：加一個原文沒有的百分比。"""
    item = _run(
        "建置內部部署流程，導入 CI/CD，團隊五人",
        "導入 CI/CD，使部署時間縮短 30%",
    )
    assert item.invented_numbers == ["30%"]
    assert not item.safe
    assert "30%" in item.verification_note


def test_number_already_in_source_is_allowed():
    item = _run("團隊五人，導入 CI/CD 共 3 條流程", "導入 CI/CD 共 3 條流程，帶領團隊五人")
    assert item.invented_numbers == []


def test_fabricated_original_is_caught():
    """模型宣稱的原句根本不在履歷裡。"""
    item = _run("主導跨部門協作專案並擔任技術窗口", "擔任跨部門技術窗口")
    assert item.source_verified is False
    assert not item.safe


def test_rejected_collects_all_problems():
    rep = _verify(
        RewriteReport(
            items=[
                RewriteItem(original="負責訂單服務的開發與維護", rewritten="負責訂單服務開發與維護"),
                RewriteItem(original="團隊五人", rewritten="帶領 10 人團隊"),
            ]
        ),
        SOURCE,
    )
    assert len(rep.rejected) == 1
    assert rep.rejected[0].invented_numbers == ["10"]
