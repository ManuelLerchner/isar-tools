# Synthetic build logs. Every recognised line uses the one evidence-backed
# format, `BUILDER: theory OWNER.THEORY 100% (Ns cumulated time)`, observed in
# real Isabelle2025 `isabelle build -v` logs; all other lines are noise that
# must be ignored. Session and theory names are made up.

import pytest

from isar_tools.stats.build import (
    BuildLog,
    BuildLogError,
    Elaboration,
    budgets_table,
    check_budgets,
    parse_build_log,
    reelaboration_table,
    reelaborations,
    session_totals,
    sessions_table,
)

LOG = """\
Building Base ...
Base: theory Base.Util 100% (2.5s cumulated time)
Base: theory HOL-Library.Monad 100% (4s cumulated time)
Finished Base (0:00:07 elapsed time)
App: theory HOL-Library.Monad 100% (3.25s cumulated time)
[12:00:01] App: theory Base.Util 100% (2.0s cumulated time)
App: theory App.Main 100% (10.0s cumulated time)
Other: theory HOL-Library.Monad 100% (5.0s cumulated time)
"""


def parse(text: str = LOG) -> BuildLog:
    return parse_build_log(text.splitlines(keepends=True))


def test_parse() -> None:
    log = parse()
    assert log.lines == 8
    assert log.elaborations[0] == Elaboration("Base", "Base", "Util", 2.5, 2)
    assert [e.line for e in log.elaborations] == [2, 3, 5, 6, 7, 8]
    assert log.elaborations[3].builder == "App"  # timestamp prefix ignored
    assert log.elaborations[1].seconds == 4.0  # integer seconds
    assert log.total_seconds == pytest.approx(26.75)
    first = log.elaborations[1]
    assert first.qualified == "HOL-Library.Monad"
    assert first.foreign
    assert not log.elaborations[0].foreign


@pytest.mark.parametrize(
    "line",
    [
        "App: theory HOL-Library.Monad 99% (3.0s cumulated time)",
        "App: theory Monad 100% (3.0s cumulated time)",
        "App: theory HOL-Library.Monad 100% (3.0.1s cumulated time)",
        "App: theory HOL-Library.Monad 100% (.5s cumulated time)",
        "App: theory HOL-Library.Monad 100% (3.0s elapsed time)",
        "App theory HOL-Library.Monad 100% (3.0s cumulated time)",
        "",
    ],
)
def test_malformed_lines_are_ignored(line: str) -> None:
    log = parse(line + "\n")
    assert log.elaborations == []
    assert log.lines == 1


def test_empty() -> None:
    log = parse("")
    assert log.lines == 0
    assert log.elaborations == []


def test_same_theory_twice_in_one_session_is_rejected() -> None:
    with pytest.raises(BuildLogError, match=r"line 3: session A elaborates B\.T again \(first"):
        parse(
            "A: theory B.T 100% (1.0s cumulated time)\n"
            "x\n"
            "A: theory B.T 100% (1.0s cumulated time)\n"
        )


def test_session_totals() -> None:
    totals = session_totals(parse())
    assert [(t.session, t.theories, t.foreign_theories) for t in totals] == [
        ("App", 3, 2),
        ("Base", 2, 1),
        ("Other", 1, 1),
    ]
    assert totals[0].seconds == pytest.approx(15.25)
    assert totals[0].foreign_seconds == pytest.approx(5.25)


def test_reelaborations() -> None:
    found = reelaborations(parse())
    assert [(r.theory, r.count, r.builders) for r in found] == [
        ("HOL-Library.Monad", 3, ["App", "Base", "Other"]),
        ("Base.Util", 2, ["App", "Base"]),
    ]
    assert found[0].wasted_seconds == pytest.approx(9.0)
    assert found[1].wasted_seconds == pytest.approx(2.5)


def test_reelaborations_tie_breaks_by_name() -> None:
    log = parse(
        "A: theory Z.T 100% (1s cumulated time)\n"
        "B: theory Z.T 100% (1s cumulated time)\n"
        "A: theory Y.T 100% (1s cumulated time)\n"
        "B: theory Y.T 100% (1s cumulated time)\n"
    )
    assert [r.theory for r in reelaborations(log)] == ["Y.T", "Z.T"]


def test_budgets() -> None:
    results = check_budgets(parse(), {"HOL-Library": 1, "Base": 1, "Unused": 0})
    assert [(r.session, r.elaborations, r.budget, r.ok) for r in results] == [
        ("Base", 1, 1, True),
        ("HOL-Library", 3, 1, False),
        ("Unused", 0, 0, True),
    ]
    assert results[1].message() == (
        "HOL-Library: 3 elaborations of its theories inside other sessions, budget 1 (12.2s cpu)"
    )


def test_tables() -> None:
    log = parse()
    sessions = sessions_table(log)
    assert sessions.rows[-1]["session"] == "TOTAL"
    assert sessions.rows[-1]["theories"] == 6
    one = parse("A: theory A.T 100% (1s cumulated time)\n")
    assert [r["session"] for r in sessions_table(one).rows] == ["A"]
    top = reelaboration_table(log, 1)
    assert [r["theory"] for r in top.rows] == ["HOL-Library.Monad"]
    assert top.title == "Theories elaborated more than once (2, 11.5s wasted)"
    assert len(reelaboration_table(log, 0).rows) == 2
    budgets = budgets_table(check_budgets(log, {"Base": 0}))
    assert budgets.rows == [
        {"session": "Base", "elaborations": 1, "budget": 0, "cpu_seconds": 2.0, "ok": False}
    ]
