"""``attributes`` group: attributes that can live beside their declaration.

``inline-declare`` reports a ``declare`` immediately after the definition,
single named theorem, or single-predicate inductive declaration that owns its
fact. Comments may separate them; intervening commands and context boundaries
are never crossed. For definitions, attributes belong on the equation after
``where``, not on the constant. Attributes on ``p.intros`` go on every rule.

Fixes require ``--fix=all``: moving registration into a command can affect its
internal processing. Only common registration attributes (``simp``, ``intro``,
``elim``, ``dest``, ``iff``, ``code``, ``code_unfold``, ``code_post``) are fixed.
Custom attributes and declarations containing comments are report-only.
Theorem-transforming attributes such as ``symmetric`` and ``of`` are excluded:
inlining them would change the stored fact. Attribute deletion is excluded too.
Generated facts from other packages, selected facts, explicit targets, and
declarations of multiple facts are outside this check's scope.

Separate configuration can be intentional even next to a declaration. Keep it
with ``(* isar-ignore: inline-declare *)`` on the ``declare`` line or immediately
before it. Imported facts and later policy changes are left alone automatically.
"""

from dataclasses import dataclass
from pathlib import Path

from isar_tools.checks.findings import Edit, Finding, Fix
from isar_tools.project.hierarchy import bracket_group
from isar_tools.source.lexer import LAYOUT, Kind, Token
from isar_tools.source.theory import Command, Theory, significant, unquote

_GOALS = frozenset({"lemma", "theorem", "corollary", "proposition"})
_NAMES = frozenset({Kind.WORD, Kind.STRING})
_TRANSFORMING = frozenset(
    {
        "OF",
        "THEN",
        "of",
        "where",
        "symmetric",
        "simplified",
        "unfolded",
        "folded",
        "rotated",
        "standard",
        "abs_def",
        "atomize",
        "rulify",
        "zero_var_indexes",
        "eta_long",
        "export_format",
        "trim_context",
        "transferred",
        "THEN_ALL_NEW",
    }
)
_REGISTRATION = frozenset(
    {"simp", "intro", "elim", "dest", "iff", "code", "code_unfold", "code_post"}
)


@dataclass(frozen=True)
class _Binding:
    name: str
    anchor: int
    attributes: tuple[Token, ...] = ()
    colon: bool = True

    def edit(self, attributes: str) -> Edit:
        if self.attributes:
            close = self.attributes[-1].start
            prefix = ", " if len(self.attributes) > 2 else ""
            return Edit(close, close, prefix + attributes)
        return Edit(self.anchor, self.anchor, f" [{attributes}]" + ("" if self.colon else ":"))


def _binding(toks: list[Token], i: int) -> tuple[_Binding, int] | None:
    if i >= len(toks) or toks[i].kind not in _NAMES:
        return None
    name = toks[i]
    i += 1
    attrs: list[Token] = []
    if i < len(toks) and toks[i].text == "[":
        attrs, i = bracket_group(toks, i)
        if attrs[-1].text != "]":
            return None
    if i >= len(toks) or toks[i].text != ":":
        return None
    return _Binding(unquote(name), name.end, tuple(attrs)), i + 1


def _sites(command: Command, theory: Theory, fact: str) -> list[_Binding]:
    toks = list(significant(command.tokens(theory.tokens)))
    # Explicit targets can export a different fact or register in another context.
    if len(toks) < 2 or toks[1].kind not in _NAMES:
        return []
    if command.name in _GOALS:
        binding = _binding(toks, 1)
        if (
            binding
            and binding[0].name == fact
            and not any(t.text in {"and", "obtains"} for t in toks[binding[1] :])
        ):
            return [binding[0]]
        return []
    if command.name not in {"definition", "inductive", "inductive_set", "coinductive"}:
        return []
    where = next((i for i, t in enumerate(toks) if t.text == "where"), -1)
    params = next((i for i, t in enumerate(toks[:where]) if t.text == "for"), where)
    if where < 0 or any(t.text == "and" for t in toks[2:params]):
        return []
    if command.name == "definition":
        binding = _binding(toks, where + 1)
        if binding:
            return [binding[0]] if binding[0].name == fact else []
        i = where + 1
        attrs: list[Token] = []
        if i < len(toks) and toks[i].text == "[":
            attrs, i = bracket_group(toks, i)
            if attrs[-1].text != "]" or i >= len(toks) or toks[i].text != ":":
                return []
            i += 1
        if i >= len(toks) or toks[i].kind not in {Kind.STRING, Kind.CARTOUCHE}:
            return []
        if unquote(toks[1]) + "_def" != fact:
            return []
        return [_Binding(fact, toks[where].end, tuple(attrs), colon=False)]
    if fact != unquote(toks[1]) + ".intros":
        return []
    rules: list[_Binding] = []
    i = where + 1
    while i < len(toks):
        binding = _binding(toks, i)
        if binding is None:
            return []
        rule, i = binding
        if i >= len(toks) or toks[i].kind not in {Kind.STRING, Kind.CARTOUCHE}:
            return []
        rules.append(rule)
        i += 1
        if i == len(toks):
            break
        if toks[i].text != "|":
            return []
        i += 1
    return rules


def _attribute_parts(tokens: list[Token]) -> list[tuple[str, ...]]:
    parts: list[tuple[str, ...]] = []
    start = depth = 0
    for i, tok in enumerate(tokens):
        depth += {"[": 1, "(": 1, "]": -1, ")": -1}.get(tok.text, 0)
        if tok.text == "," and depth == 0:
            parts.append(tuple(unquote(t) for t in tokens[start:i]))
            start = i + 1
    parts.append(tuple(unquote(t) for t in tokens[start:]))
    return parts


def _fixable(parts: list[tuple[str, ...]]) -> bool:
    for part in parts:
        if not part or part[0] not in _REGISTRATION:
            return False
        if len(part) == 1:
            continue
        if part[0] in {"simp", "iff"} and part[1:] == ("add",):
            continue
        if part[0] in {"intro", "elim", "dest"} and part[1:] in {("!",), ("?",)}:
            continue
        return False
    return True


def _removal(theory: Theory, command: Command) -> Edit:
    start, end = theory.start(command), theory.end(command)
    line_start = theory.text.rfind("\n", 0, start) + 1
    line_end = theory.text.find("\n", end)
    if (
        line_end >= 0
        and not theory.text[line_start:start].strip()
        and not theory.text[end:line_end].strip()
    ):
        return Edit(line_start, line_end + 1)
    return Edit(start, end)


def check_attributes(path: Path, theory: Theory) -> list[Finding]:
    findings: list[Finding] = []
    # Only a completed theory-level proof can own a following declaration.
    goals = {
        block.stop: block.statement
        for block in theory.goal_blocks()
        if block.closed and theory.commands[block.stop - 1].name not in {"oops", "sorry"}
    }
    for i, command in enumerate(theory.commands):
        if command.name != "declare" or i == 0:
            continue
        toks = list(significant(command.tokens(theory.tokens)))
        if len(toks) < 5 or toks[1].kind not in _NAMES or toks[2].text != "[":
            continue
        attrs, stop = bracket_group(toks, 2)
        if stop != len(toks) or attrs[-1].text != "]":
            continue
        parts = _attribute_parts(attrs[1:-1])
        if any(not p or p[0] in _TRANSFORMING or "del" in p for p in parts):
            continue
        fact = unquote(toks[1])
        owner = theory.commands[goals.get(i, i - 1)]
        if owner.name in _GOALS and i not in goals:
            continue
        sites = _sites(owner, theory, fact)
        if not sites:
            continue
        raw_tokens = command.tokens(theory.tokens)
        has_comments = any(t.kind is Kind.COMMENT for t in raw_tokens) or len(
            list(significant(raw_tokens))
        ) != len([t for t in raw_tokens if t.kind not in LAYOUT])
        fix = None
        if _fixable(parts) and not has_comments:
            text = theory.text[attrs[0].end : attrs[-1].start]
            fix = Fix((*(s.edit(text) for s in sites), _removal(theory, command)), False)
        findings.append(
            Finding.at(
                path,
                theory.lines,
                theory.start(command),
                "inline-declare",
                f"{fact}: attach attributes to the preceding {owner.name}"
                + (" (review custom attributes or comments manually)" if fix is None else ""),
                fix,
            )
        )
    return findings
