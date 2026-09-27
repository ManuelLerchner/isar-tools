"""Statistics views: tables over the metrics of many theories."""

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from isar_tools.render import Cell, Column, Table, display_path
from isar_tools.stats.metrics import ProofStats, TheoryStats

# Commands that introduce a definition, datatype, or other named entity.
DEFINITIONS = frozenset(
    {
        "definition",
        "abbreviation",
        "fun",
        "function",
        "primrec",
        "primcorec",
        "corec",
        "partial_function",
        "datatype",
        "codatatype",
        "record",
        "type_synonym",
        "typedecl",
        "typedef",
        "inductive",
        "inductive_set",
        "coinductive",
        "coinductive_set",
        "consts",
        "axiomatization",
        "locale",
        "class",
        "lift_definition",
        "quotient_type",
        "quotient_definition",
        "nominal_datatype",
        "nominal_primrec",
        "fixrec",
        "domain",
    }
)


@dataclass(frozen=True)
class Entry:
    session: str
    path: Path
    stats: TheoryStats

    @property
    def theory(self) -> str:
        return self.stats.name or self.path.stem


def _mean(xs: Sequence[int]) -> float:
    return statistics.fmean(xs) if xs else 0.0


def _median(xs: Sequence[int]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def percentile(xs: Sequence[int], q: float) -> int:
    """Nearest-rank percentile, 0 for no data."""
    if not xs:
        return 0
    ordered = sorted(xs)
    rank = max(1, math.ceil(len(ordered) * q / 100))
    return ordered[rank - 1]


def _definitions(stats: TheoryStats) -> int:
    return sum(n for name, n in stats.commands.items() if name in DEFINITIONS)


def _unfinished(proofs: Sequence[ProofStats]) -> int:
    return sum(len(p.unfinished) for p in proofs)


def _by_session(entries: Sequence[Entry]) -> dict[str, list[Entry]]:
    groups: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        groups[entry.session].append(entry)
    return groups


def sessions_table(entries: Sequence[Entry]) -> Table:
    def row(session: str, group: Sequence[Entry]) -> dict[str, Cell]:
        proofs = [p.proof_lines for e in group for p in e.stats.proofs]
        lines = sum(e.stats.lines for e in group)
        doc = sum(e.stats.doc_lines for e in group)
        return {
            "session": session,
            "theories": len(group),
            "lines": lines,
            "code_lines": sum(e.stats.code_lines for e in group),
            "doc_lines": doc,
            "doc_percent": round(100 * doc / lines, 1) if lines else 0.0,
            "definitions": sum(_definitions(e.stats) for e in group),
            "proofs": len(proofs),
            "mean_proof": round(_mean(proofs), 1),
            "median_proof": _median(proofs),
            "p90_proof": percentile(proofs, 90),
            "max_proof": max(proofs, default=0),
            "unfinished": sum(_unfinished(e.stats.proofs) for e in group),
        }

    rows = [row(s, g) for s, g in _by_session(entries).items()]
    rows.sort(key=lambda r: (-int(r["lines"]), str(r["session"])))
    if len(rows) > 1:
        rows.append(row("TOTAL", entries))
    return Table(
        "sessions",
        "Sessions by lines",
        [
            Column("session", "session"),
            Column("theories", "theories", True),
            Column("lines", "lines", True),
            Column("code_lines", "code", True),
            Column("doc_lines", "doc", True),
            Column("doc_percent", "doc%", True),
            Column("definitions", "defs", True),
            Column("proofs", "proofs", True),
            Column("mean_proof", "mean proof", True),
            Column("median_proof", "median", True),
            Column("p90_proof", "p90", True),
            Column("max_proof", "max", True),
            Column("unfinished", "unfinished", True),
        ],
        rows,
    )


THEORY_SORTS: dict[str, Callable[[Entry], tuple[float | str, ...]]] = {
    "lines": lambda e: (-e.stats.lines, e.theory),
    "code": lambda e: (-e.stats.code_lines, e.theory),
    "doc": lambda e: (-e.stats.doc_lines, e.theory),
    "proofs": lambda e: (-len(e.stats.proofs), e.theory),
    "max-proof": lambda e: (-max((p.proof_lines for p in e.stats.proofs), default=0), e.theory),
    "name": lambda e: (e.session, e.theory),
}


def theories_table(entries: Sequence[Entry], sort: str = "lines", top: int = 0) -> Table:
    ordered = sorted(entries, key=THEORY_SORTS[sort])
    shown = ordered[:top] if top else ordered
    rows: list[dict[str, Cell]] = []
    for e in shown:
        proofs = [p.proof_lines for p in e.stats.proofs]
        rows.append(
            {
                "session": e.session,
                "theory": e.theory,
                "path": display_path(e.path),
                "lines": e.stats.lines,
                "code_lines": e.stats.code_lines,
                "doc_lines": e.stats.doc_lines,
                "blank_lines": e.stats.blank_lines,
                "definitions": _definitions(e.stats),
                "proofs": len(proofs),
                "mean_proof": round(_mean(proofs), 1),
                "max_proof": max(proofs, default=0),
                "long_lines": len(e.stats.long_lines),
                "unfinished": _unfinished(e.stats.proofs),
            }
        )
    suffix = f" (top {len(shown)} of {len(ordered)})" if len(shown) < len(ordered) else ""
    return Table(
        "theories",
        f"Theories by {sort}{suffix}",
        [
            Column("session", "session"),
            Column("theory", "theory"),
            Column("lines", "lines", True),
            Column("code_lines", "code", True),
            Column("doc_lines", "doc", True),
            Column("blank_lines", "blank", True),
            Column("definitions", "defs", True),
            Column("proofs", "proofs", True),
            Column("mean_proof", "mean proof", True),
            Column("max_proof", "max proof", True),
            Column("long_lines", "long lines", True),
            Column("unfinished", "unfinished", True),
            Column("path", "path"),
        ],
        rows,
    )


def proofs_table(entries: Sequence[Entry], top: int = 0) -> Table:
    proofs = [(e, p) for e in entries for p in e.stats.proofs]
    proofs.sort(key=lambda ep: (-ep[1].proof_lines, ep[0].theory, ep[1].line))
    shown = proofs[:top] if top else proofs
    rows: list[dict[str, Cell]] = [
        {
            "session": e.session,
            "theory": e.theory,
            "name": p.name,
            "line": p.line,
            "command": p.command,
            "statement_lines": p.statement_lines,
            "proof_lines": p.proof_lines,
            "lines": p.lines,
            "closed": p.closed,
            "unfinished": " ".join(p.unfinished),
            "path": display_path(e.path),
        }
        for e, p in shown
    ]
    suffix = f" (top {len(shown)} of {len(proofs)})" if len(shown) < len(proofs) else ""
    return Table(
        "proofs",
        f"Longest proofs{suffix}",
        [
            Column("session", "session"),
            Column("theory", "theory"),
            Column("name", "name"),
            Column("line", "line", True),
            Column("command", "command"),
            Column("statement_lines", "statement", True),
            Column("proof_lines", "proof", True),
            Column("lines", "total", True),
            Column("closed", "closed"),
            Column("unfinished", "unfinished"),
            Column("path", "path"),
        ],
        rows,
    )


def commands_table(entries: Sequence[Entry]) -> Table:
    counts: Counter[tuple[str, str]] = Counter()
    for e in entries:
        for name, n in e.stats.commands.items():
            counts[(e.session, name)] += n
    rows: list[dict[str, Cell]] = [
        {"session": session, "command": name, "count": n}
        for (session, name), n in sorted(
            counts.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1])
        )
    ]
    return Table(
        "commands",
        "Commands per session",
        [
            Column("session", "session"),
            Column("command", "command"),
            Column("count", "count", True),
        ],
        rows,
    )


def style_table(entries: Sequence[Entry], *, max_theory_lines: int) -> Table:
    rows: list[dict[str, Cell]] = []
    for e in entries:
        s = e.stats
        unfinished = _unfinished(s.proofs)
        too_long = s.lines > max_theory_lines
        if not (too_long or s.long_lines or unfinished or s.methods):
            continue
        rows.append(
            {
                "session": e.session,
                "theory": e.theory,
                "lines": s.lines,
                "over_max_lines": too_long,
                "long_lines": len(s.long_lines),
                "unfinished": unfinished,
                "methods": " ".join(f"{m}={n}" for m, n in sorted(s.methods.items())),
                "path": display_path(e.path),
            }
        )
    rows.sort(key=lambda r: (not r["over_max_lines"], -int(r["long_lines"]), str(r["theory"])))
    return Table(
        "style",
        f"Style watchlist (theories over {max_theory_lines} lines, long lines, "
        "unfinished proofs, watched methods)",
        [
            Column("session", "session"),
            Column("theory", "theory"),
            Column("lines", "lines", True),
            Column("over_max_lines", "too long"),
            Column("long_lines", "long lines", True),
            Column("unfinished", "unfinished", True),
            Column("methods", "methods"),
            Column("path", "path"),
        ],
        rows,
    )
