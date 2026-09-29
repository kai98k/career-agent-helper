"""澄清流程的程式部分。不打模型。"""

from app.schemas.clarify import Answer, ClarifyingQuestion, ClarifyReport
from app.schemas.matching import MatchReport, MatchVerdict, RequirementMatch
from app.services import clarifier
from app.services.matcher import _verify

RESUME = """- 依照 PM 需求調整既有報表的計算邏輯，並撰寫單元測試
"""


def _m(req, verdict, quote=None):
    return RequirementMatch(requirement=req, verdict=verdict, quote=quote)


def test_candidates_are_not_found_and_indirect_only():
    rep = MatchReport(matches=[
        _m("Java", MatchVerdict.DIRECT, "Java"),
        _m("SQL", MatchVerdict.NOT_FOUND),
        _m("HTTP 狀態碼", MatchVerdict.INDIRECT, "RESTful API"),
    ])
    assert clarifier.candidates(rep) == ["SQL", "HTTP 狀態碼"]


def test_questions_outside_candidates_are_dropped():
    """模型自己加一題不在清單裡的，程式直接丟掉。"""
    rep = ClarifyReport(questions=[
        ClarifyingQuestion(requirement="SQL", question="你有寫過 SQL 嗎？"),
        ClarifyingQuestion(requirement="領導能力", question="你帶過人嗎？"),
    ])
    out = clarifier._verify(rep, ["SQL"])
    assert [q.requirement for q in out.questions] == ["SQL"]


def test_question_count_is_capped_by_code():
    reqs = [f"要求{i}" for i in range(5)]
    rep = ClarifyReport(questions=[ClarifyingQuestion(requirement=r, question="?") for r in reqs])
    assert len(clarifier._verify(rep, reqs).questions) == clarifier.MAX_QUESTIONS


def test_blank_answers_are_skipped():
    text = clarifier.supplement([
        Answer(requirement="SQL", answer="報表有自己寫 JOIN"),
        Answer(requirement="Docker", answer="   "),
    ])
    assert "SQL" in text and "Docker" not in text


def test_quote_from_supplement_is_tagged_as_user_answer():
    """引用落在補充段落的，要標成使用者說的，不是履歷寫的。"""
    sup = clarifier.supplement([Answer(requirement="SQL", answer="報表有自己寫 JOIN")])
    source = f"{RESUME}\n\n{clarifier.SUPPLEMENT_HEADER}\n{sup}"
    rep = MatchReport(matches=[
        _m("單元測試", MatchVerdict.DIRECT, "並撰寫單元測試"),
        _m("SQL", MatchVerdict.DIRECT, "報表有自己寫 JOIN"),
    ])
    out = _verify(rep, source, boundary=len(RESUME))
    assert [m.quote_source for m in out.matches] == ["resume", "user_answer"]
    assert all(m.quote_verified for m in out.matches)
