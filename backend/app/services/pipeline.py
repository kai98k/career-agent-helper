"""固定流程（路徑 A）。

這是 Day 07 到 Day 13 長出來的那條路：解析 → 對照 → 改寫 → 計畫，
每一步都是寫死的順序，沒有任何決策空間。

**這條路不會被 agent 取代。** Day 29 要比較「固定流程 vs agent」的品質、
延遲與成本，兩條路徑必須同時活著，而且共用同一組底層驗證邏輯，
否則比較的會是兩份寫得不一樣的程式碼，不是 agent 這一層的價值。
"""

import time

from app.schemas.clarify import Answer
from app.schemas.report import AnalysisReport, UsageSummary
from app.services import clarifier, matcher, parser, planner, rewriter
from app.services.llm import Usage


def _summary(u: Usage, calls: int) -> UsageSummary:
    return UsageSummary(
        prompt_tokens=u.prompt_tokens,
        thought_tokens=u.thought_tokens,
        output_tokens=u.output_tokens,
        total_tokens=u.total_tokens,
        calls=calls,
    )


def _gaps_text(report) -> str:
    """把對照結果整理成計畫生成要吃的輸入。

    只餵「找不到證據」的項目，因為計畫要補的是缺口。
    有明確證據的那些不需要再學一次。

    第一版這裡寫的是「缺：」，模型照字面讀，幫一年經驗的後端排了四週 SQL 入門。
    not_found 的意思是履歷沒寫，不是不會，給計畫的字眼也要照這個意思寫。
    """
    lines = []
    for m in report.matches:
        if m.verdict.value == "not_found":
            lines.append(f"- 履歷沒有證據（不確定會不會）：{m.requirement}")
        elif m.verdict.value == "indirect":
            lines.append(f"- 證據薄弱：{m.requirement}（{m.reasoning}）")
    return "\n".join(lines) or "（沒有明顯缺口）"


def run(
    resume_text: str,
    job_text: str | None = None,
    *,
    do_rewrite: bool = True,
    do_plan: bool = True,
    weekly_hours: float = 10.0,
    do_clarify: bool = True,
    answers: list[Answer] | None = None,
) -> AnalysisReport:
    started = time.perf_counter()
    usage = Usage()
    calls = 0

    r = parser.parse_resume(resume_text)
    usage, calls = usage + r.usage, calls + 1
    report = AnalysisReport(path="pipeline", model=r.model, resume=r.data)

    if job_text:
        j = parser.parse_job(job_text)
        usage, calls = usage + j.usage, calls + 1
        report.job = j.data

        supplement = clarifier.supplement(answers or [])
        m = matcher.match(j.data, resume_text, supplement or None)
        usage, calls = usage + m.usage, calls + 1
        report.matching = m.data
        report.answers = answers or []

        # 還沒回答過才問。回答過的那一輪直接往下走，不再追問第二輪。
        if do_clarify and not answers:
            c = clarifier.ask(resume_text, m.data)
            if c is not None:
                usage, calls = usage + c.usage, calls + 1
                report.questions = c.data.questions

    if do_rewrite:
        w = rewriter.rewrite(resume_text, job_text)
        usage, calls = usage + w.usage, calls + 1
        report.rewrite = w.data

    # 還有問題沒回答，就先不排計畫。第一版照樣排，結果畫面上一邊問「你會 SQL 嗎」，
    # 下面已經幫他排好兩週 SQL 入門，等於問了也沒在等答案。
    if do_plan and report.matching and not report.questions:
        validated, p = planner.generate_and_validate(
            _gaps_text(report.matching), weekly_hours=weekly_hours
        )
        usage, calls = usage + p.usage, calls + 1
        report.plan = validated

    report.usage = _summary(usage, calls)
    report.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return report
