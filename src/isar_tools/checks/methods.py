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

from isar_tools.checks.findings import Finding
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


def _entries(toks: list[Token], i: int) -> tuple[list[tuple[str, Token]], int]:
    """The entries of the list starting at ``toks[i]``, as text with their
    first token, and the index after the list. An entry is a name or literal
    with its attributes: ``foo[symmetric]``."""
    entries: list[tuple[str, Token]] = []
    while i < len(toks) and toks[i].text not in _LIST_END and not _modifier(toks, i):
        first = toks[i]
        if first.text in ("(", "["):
            _, i = bracket_group(toks, i)  # a nested method or an anonymous attribute
            continue
        i += 1
        text = first.text
        if i < len(toks) and toks[i].text == "[":
            group, i = bracket_group(toks, i)
            text += "[" + " ".join(t.text for t in group[1:-1]) + "]"
        entries.append((text, first))
    return entries, i


def _findings(toks: list[Token]) -> Iterator[tuple[Token, str, str]]:
    """``(token, code, message)`` for the modifiers of one method text."""
    i = 1
    while i < len(toks):
        if not _modifier(toks, i):
            i += 1
            continue
        modifier = toks[i]
        entries, i = _entries(toks, i + 2)
        if not entries:
            yield modifier, "empty-modifier", f"{modifier.text}: lists nothing"
        seen: set[str] = set()
        for text, tok in entries:
            if text in seen:
                yield tok, "duplicate-fact", f"{text} is listed twice after {modifier.text}:"
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
        Finding.at(path, theory.lines, tok.start, code, message)
        for command in theory.commands
        if command.name in _METHOD_COMMANDS
        for tok, code, message in _findings(list(significant(command.tokens(theory.tokens))))
    ]
    for command in _single_applies(theory):
        message = "one apply and done: write by"
        findings.append(
            Finding.at(path, theory.lines, theory.start(command), "single-apply", message)
        )
    return findings
