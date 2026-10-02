"""``methods`` group: proof method arguments that do nothing.

A method modifier introduces a list: ``simp add: a b``, ``auto intro: c``,
``induct arbitrary: x rule: r``. Isabelle accepts an empty list, so
``by (simp add:)`` builds and reads as if it used a fact.

- ``empty-modifier``: a modifier with nothing after it, before ``)``, ``,``,
  ``|``, ``;``, the next modifier, or the end of the method;
- ``duplicate-fact``: an entry listed twice in one modifier's list, with the
  same attributes.

Only the method text of ``by``, ``apply``, ``apply_end``, ``proof``, and
``qed`` is read.

- ``single-apply``: a goal proved by ``apply m`` and ``done`` alone, which
  ``by m`` says in one step.
"""

from collections.abc import Iterator
from pathlib import Path

from isar_tools.checks.findings import Edit, Finding, Fix
from isar_tools.project.hierarchy import bracket_group
from isar_tools.source.keywords import PROOF_GOALS, THEORY_GOALS
from isar_tools.source.lexer import Kind, Token
from isar_tools.source.theory import Command, Theory, significant

_METHOD_COMMANDS = frozenset({"by", "apply", "apply_end", "proof", "qed"})
# Commands between a goal and its proof that `by` keeps before it.
_CHAINING = frozenset({"using", "unfolding", "including", "supply"})
# Tokens that end a modifier's list.
_LIST_END = frozenset({")", ",", "|", ";", "]"})


def _modifier(toks: list[Token], i: int) -> bool:
    """Whether ``toks[i]`` starts a modifier: ``add:``."""
    return toks[i].kind is Kind.WORD and i + 1 < len(toks) and toks[i + 1].text == ":"


def _entries(toks: list[Token], i: int) -> tuple[list[tuple[str, int, int]], int]:
    """The entries of the list starting at ``toks[i]``, as text with the
    index of their first token and the index after them, and the index after
    the list. An entry is a name or literal with its attributes:
    ``foo[symmetric]``."""
    entries: list[tuple[str, int, int]] = []
    while i < len(toks) and toks[i].text not in _LIST_END and not _modifier(toks, i):
        start = i
        if toks[i].text in ("(", "["):
            _, i = bracket_group(toks, i)  # a nested method or an anonymous attribute
            continue
        i += 1
        text = toks[start].text
        if i < len(toks) and toks[i].text == "[":
            group, i = bracket_group(toks, i)
            text += "[" + " ".join(t.text for t in group[1:-1]) + "]"
        entries.append((text, start, i))
    return entries, i


def _cut(toks: list[Token], first: int, stop: int) -> Fix:
    """Delete ``toks[first:stop]`` and the space before them."""
    return Fix((Edit(toks[first - 1].end, toks[stop - 1].end),), safe=True)


def _empty_modifier_fix(toks: list[Token], i: int) -> Fix:
    """``(simp add:)`` is ``simp``; elsewhere the modifier just goes."""
    if (
        i >= 2
        and toks[i - 2].text == "("
        and toks[i - 1].kind is Kind.WORD
        and i + 2 < len(toks)
        and toks[i + 2].text == ")"
    ):
        return Fix((Edit(toks[i - 2].start, toks[i + 2].end, toks[i - 1].text),), safe=True)
    return _cut(toks, i, i + 2)


def _findings(toks: list[Token]) -> Iterator[tuple[Token, str, str, Fix]]:
    """``(token, code, message, fix)`` for the modifiers of one method text."""
    i = 1
    while i < len(toks):
        if not _modifier(toks, i):
            i += 1
            continue
        modifier = i
        entries, i = _entries(toks, i + 2)
        name = toks[modifier].text
        if not entries:
            fix = _empty_modifier_fix(toks, modifier)
            yield toks[modifier], "empty-modifier", f"{name}: lists nothing", fix
        seen: set[str] = set()
        for text, first, stop in entries:
            if text in seen:
                message = f"{text} is listed twice after {name}:"
                yield toks[first], "duplicate-fact", message, _cut(toks, first, stop)
            seen.add(text)


def _single_applies(theory: Theory) -> Iterator[Command]:
    """``apply m`` directly between a goal (with its ``using`` and
    ``unfolding``) and ``done``: the goal is ``by m``."""
    commands = theory.commands
    for i, command in enumerate(commands):
        if command.name != "done" or i < 2 or commands[i - 1].name != "apply":
            continue
        k = i - 2
        while k > 0 and commands[k].name in _CHAINING:
            k -= 1
        if commands[k].kind in THEORY_GOALS | PROOF_GOALS:
            yield commands[i - 1]


def check_methods(path: Path, theory: Theory) -> list[Finding]:
    findings = [
        Finding.at(path, theory.lines, tok.start, code, message, fix)
        for command in theory.commands
        if command.name in _METHOD_COMMANDS
        for tok, code, message, fix in _findings(list(significant(command.tokens(theory.tokens))))
    ]
    for command in _single_applies(theory):
        message = "one apply and done: write by"
        findings.append(
            Finding.at(path, theory.lines, theory.start(command), "single-apply", message)
        )
    return findings
