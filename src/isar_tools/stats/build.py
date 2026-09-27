"""Build statistics: where theory elaboration time went in an Isabelle build.

A session inherits the heaps of its parent chain and nothing else. A theory
owned by a session that is not an ancestor of the importing session is
elaborated again inside the importing session, once per importing session. The
build stays green and the only symptom is time, so this reads what a build
actually did from its log.

Produce a log with ``isabelle build -v ... > build.log``.

Recognised log format
---------------------

Exactly one line shape is recognised, the one observed in real Isabelle2025
``isabelle build -v`` logs (the Voblint prototype
``scripts/check_build_reelaboration.py`` was written against them)::

    BUILDER: theory OWNER.THEORY 100% (SECONDSs cumulated time)

``BUILDER`` is the session being built, ``OWNER.THEORY`` the session-qualified
theory it elaborated. Text before ``BUILDER`` on the same line (for example a
timestamp) is ignored. Every other line is ignored: no other Isabelle log line
(``Building ...``, ``Finished ...``, timing summaries) is interpreted, because
no real sample is available to check their exact shape.

Consequently a log without any recognised line is ambiguous: either nothing was
rebuilt, or the file is not an ``isabelle build -v`` log. Callers must report
that instead of printing empty tables.
"""

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from isar_tools.render import Cell, Column, Table

# The only evidence-backed line format; see the module docstring.
LINE = re.compile(r"(\S+): theory (\S+)\.(\S+) 100% \((\d+(?:\.\d+)?)s cumulated time\)")


class BuildLogError(Exception):
    """A build log that cannot be interpreted reliably."""


@dataclass(frozen=True)
class Elaboration:
    """One theory elaborated inside one session's build."""

    builder: str  # the session whose build elaborated the theory
    owner: str  # the session the theory belongs to
    theory: str  # base name, without the owner qualifier
    seconds: float  # cumulated (cpu) time reported by Isabelle
    line: int  # 1-based line number in the log

    @property
    def qualified(self) -> str:
        return f"{self.owner}.{self.theory}"

    @property
    def foreign(self) -> bool:
        """Elaborated inside a session other than its owner."""
        return self.builder != self.owner


@dataclass(frozen=True)
class BuildLog:
    elaborations: Sequence[Elaboration]
    lines: int  # lines read, recognised or not

    @property
    def total_seconds(self) -> float:
        return sum((e.seconds for e in self.elaborations), 0.0)


def parse_build_log(lines: Iterable[str]) -> BuildLog:
    """The theory elaborations recorded in the lines of an ``isabelle build -v`` log.

    Raises :class:`BuildLogError` if a session elaborates the same theory
    twice: one build does not do that, so the log is most likely several
    builds concatenated, and totals over it would be wrong.
    """
    elaborations: list[Elaboration] = []
    seen: dict[tuple[str, str, str], int] = {}
    count = 0
    for count, text in enumerate(lines, start=1):
        match = LINE.search(text)
        if match is None:
            continue
        builder, owner, theory, seconds = match.groups()
        key = (builder, owner, theory)
        if key in seen:
            raise BuildLogError(
                f"line {count}: session {builder} elaborates {owner}.{theory} again "
                f"(first at line {seen[key]}); is this several builds in one log?"
            )
        seen[key] = count
        elaborations.append(Elaboration(builder, owner, theory, float(seconds), count))
    return BuildLog(elaborations, count)


@dataclass(frozen=True)
class SessionTotals:
    session: str
    theories: int
    foreign_theories: int
    seconds: float
    foreign_seconds: float


def session_totals(log: BuildLog) -> list[SessionTotals]:
    """Per building session, sorted by name."""
    by_builder: dict[str, list[Elaboration]] = defaultdict(list)
    for e in log.elaborations:
        by_builder[e.builder].append(e)
    return [
        SessionTotals(
            session,
            len(es),
            sum(1 for e in es if e.foreign),
            sum((e.seconds for e in es), 0.0),
            sum((e.seconds for e in es if e.foreign), 0.0),
        )
        for session, es in sorted(by_builder.items())
    ]


@dataclass(frozen=True)
class Reelaboration:
    theory: str  # OWNER.THEORY
    builders: Sequence[str]  # sessions that elaborated it, sorted
    wasted_seconds: float  # all elaborations but the cheapest

    @property
    def count(self) -> int:
        return len(self.builders)


def reelaborations(log: BuildLog) -> list[Reelaboration]:
    """Theories elaborated more than once, most wasted time first.

    Every elaboration counts, including the one in the owning session: one
    elaboration is necessary, each further one is waste. The necessary one is
    taken to be the cheapest, so waste is ``sum - min``.
    """
    by_theory: dict[str, list[Elaboration]] = defaultdict(list)
    for e in log.elaborations:
        by_theory[e.qualified].append(e)
    found = [
        Reelaboration(
            theory,
            sorted(e.builder for e in es),
            sum((e.seconds for e in es), 0.0) - min(e.seconds for e in es),
        )
        for theory, es in by_theory.items()
        if len(es) > 1
    ]
    return sorted(found, key=lambda r: (-r.wasted_seconds, r.theory))


@dataclass(frozen=True)
class BudgetResult:
    session: str
    elaborations: int  # of the session's theories, inside other sessions
    budget: int
    seconds: float

    @property
    def ok(self) -> bool:
        return self.elaborations <= self.budget

    def message(self) -> str:
        return (
            f"{self.session}: {self.elaborations} elaborations of its theories inside "
            f"other sessions, budget {self.budget} ({self.seconds:.1f}s cpu)"
        )


def check_budgets(
    log: BuildLog,
    budgets: Mapping[str, int],
    default: int | None = None,
    own: Collection[str] = (),
) -> list[BudgetResult]:
    """Foreign elaborations of each budgeted session's theories, sorted by session.

    With ``default``, every other session whose theories are elaborated inside
    other sessions is budgeted too, except the project's ``own`` sessions: a
    library dependency slipping in fails instead of costing time unnoticed.
    """
    budgets = dict(budgets)
    if default is not None:
        for e in log.elaborations:
            if e.foreign and e.owner not in own:
                budgets.setdefault(e.owner, default)
    results: list[BudgetResult] = []
    for session, budget in sorted(budgets.items()):
        foreign = [e for e in log.elaborations if e.foreign and e.owner == session]
        results.append(
            BudgetResult(session, len(foreign), budget, sum((e.seconds for e in foreign), 0.0))
        )
    return results


def _secs(seconds: float) -> float:
    """Seconds for output: sums of decimal inputs carry float noise
    (``12.4 + 1.5``); milliseconds are finer than any log reports."""
    return round(seconds, 3)


def sessions_table(log: BuildLog) -> Table:
    totals = session_totals(log)
    rows: list[dict[str, Cell]] = [
        {
            "session": t.session,
            "theories": t.theories,
            "foreign_theories": t.foreign_theories,
            "cpu_seconds": _secs(t.seconds),
            "foreign_seconds": _secs(t.foreign_seconds),
        }
        for t in totals
    ]
    if len(totals) > 1:
        rows.append(
            {
                "session": "TOTAL",
                "theories": sum(t.theories for t in totals),
                "foreign_theories": sum(t.foreign_theories for t in totals),
                "cpu_seconds": _secs(sum((t.seconds for t in totals), 0.0)),
                "foreign_seconds": _secs(sum((t.foreign_seconds for t in totals), 0.0)),
            }
        )
    return Table(
        "sessions",
        "Theory elaboration per building session (cpu seconds)",
        [
            Column("session", "session"),
            Column("theories", "theories", True),
            Column("foreign_theories", "foreign", True),
            Column("cpu_seconds", "cpu s", True),
            Column("foreign_seconds", "foreign s", True),
        ],
        rows,
    )


def reelaboration_table(log: BuildLog, top: int) -> Table:
    found = reelaborations(log)
    waste = sum((r.wasted_seconds for r in found), 0.0)
    shown = found[:top] if top else found
    return Table(
        "reelaborated",
        f"Theories elaborated more than once ({len(found)}, {waste:.1f}s wasted)",
        [
            Column("theory", "theory"),
            Column("elaborations", "x", True),
            Column("wasted_seconds", "wasted s", True),
            Column("sessions", "sessions"),
        ],
        [
            {
                "theory": r.theory,
                "elaborations": r.count,
                "wasted_seconds": _secs(r.wasted_seconds),
                "sessions": " ".join(r.builders),
            }
            for r in shown
        ],
    )


def budgets_table(results: Sequence[BudgetResult]) -> Table:
    return Table(
        "budgets",
        "Elaborations of a session's theories inside other sessions",
        [
            Column("session", "session"),
            Column("elaborations", "elaborations", True),
            Column("budget", "budget", True),
            Column("cpu_seconds", "cpu s", True),
            Column("ok", "ok"),
        ],
        [
            {
                "session": r.session,
                "elaborations": r.elaborations,
                "budget": r.budget,
                "cpu_seconds": _secs(r.seconds),
                "ok": r.ok,
            }
            for r in results
        ],
    )
