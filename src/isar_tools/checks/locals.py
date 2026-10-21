"""``unused-local``: a named fact of a proof that nothing after it cites."""

import re
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path

from isar_tools.checks.findings import Finding
from isar_tools.project.hierarchy import bracket_group
from isar_tools.source.keywords import CommandKind
from isar_tools.source.lexer import Kind, Token
from isar_tools.source.theory import Command, Theory, proof_steps, significant, unquote

# Commands that name facts, and the separator after the name: `have h: ...`,
# `note h = ...`. `show` and `thus` are left out: their facts close the goal.
_BINDERS = {
    "have": ":",
    "hence": ":",
    "obtain": ":",
    "assume": ":",
    "presume": ":",
    "define": ":",
    "note": "=",
}
# Words after which a statement names its fact; `obtain` and `define` name
# theirs after `where`.
_STARTS = frozenset({"and", "where"})
# Words that end the statements: the premises and parameters of `if` and
# `for` are local to the fact's own proof.
_ENDS = frozenset({"if", "for", "when"})
# Tokens whose text can hold method text, and a word inside one.
_QUOTED = frozenset({Kind.STRING, Kind.CARTOUCHE, Kind.ALT_STRING})
_WORD = re.compile(r"[\w']+")
# Commands that use the previous fact without its name.
_CHAINING = frozenset({"hence", "thus", "moreover", "also"})


@dataclass
class _Binding:
    token: Token
    command: str
    after: int  # citations count from this offset on
    anonymous: bool = False  # the next command chains the fact as `this`


@dataclass
class _Frame:
    """A goal's proof, or a ``{ }`` block, with the facts named in it."""

    bindings: dict[str, _Binding] = field(default_factory=dict[str, _Binding])
    # Facts the goal that opened the frame names, bound once its proof ends.
    pending: list[_Binding] = field(default_factory=list[_Binding])


def _names(command: Command, toks: list[Token]) -> list[Token]:
    """The tokens naming the facts ``command`` binds."""
    separator = _BINDERS.get(command.name)
    if separator is None:
        return []
    found: list[Token] = []
    i = 1
    while i < len(toks) and toks[i].text not in _ENDS:
        if toks[i].text in ("[", "("):  # attributes and patterns bind nothing
            _, i = bracket_group(toks, i)
            continue
        at_start = i == 1 or toks[i - 1].text in _STARTS
        if at_start and toks[i].kind in (Kind.WORD, Kind.STRING):
            j = i + 1
            if j < len(toks) and toks[j].text == "[":
                _, j = bracket_group(toks, j)
            if j < len(toks) and toks[j].text == separator:
                found.append(toks[i])
        i += 1
    return found


def _chains(theory: Theory, index: int) -> bool:
    """Whether ``commands[index]`` uses the previous fact without its name."""
    if index >= len(theory.commands):
        return False
    command = theory.commands[index]
    if command.kind is CommandKind.PRF_CHAIN or command.name in _CHAINING:
        return True
    return any(t.text == "this" for t in command.tokens(theory.tokens))


def check_unused_locals(path: Path, theory: Theory, allowed: frozenset[str]) -> list[Finding]:
    # A local fact is cited by a word of formal text: `h`, `h(1)`, `h[OF x]`,
    # and numerals such as `1`, which names of declarations cannot be. Method
    # text nests in cartouches (`use h in \<open>simp add: g\<close>`), so a word
    # inside a string or cartouche counts too; a term's variable of the same
    # name then hides a finding rather than invents one.
    cited: dict[str, list[int]] = {}
    for tok in theory.tokens:
        if tok.kind is Kind.WORD:
            cited.setdefault(tok.text, []).append(tok.start)
        elif tok.kind in _QUOTED:
            for m in _WORD.finditer(tok.text):
                cited.setdefault(m.group(), []).append(tok.start + m.start())
    findings: list[Finding] = []

    def settle(binding: _Binding, end: int, rebinding: int = -1) -> None:
        """Report ``binding`` if no use of its name lies before ``end``, other
        than the token at ``rebinding`` that binds the name again."""
        name = unquote(binding.token)
        offsets = cited.get(name, [])
        uses = offsets[bisect_left(offsets, binding.after) : bisect_left(offsets, end)]
        if name in allowed or binding.anonymous or any(o != rebinding for o in uses):
            return
        message = f"{binding.command} {name} is cited nowhere in its proof"
        findings.append(
            Finding.at(path, theory.lines, binding.token.start, "unused-local", message)
        )

    def bind(frame: _Frame, binding: _Binding) -> None:
        name = unquote(binding.token)
        # Rebound: the old fact stays in reach until the new one is bound, so
        # `have h: ... using h` and `note h = h[symmetric]` cite the old one.
        if name in frame.bindings:
            settle(frame.bindings[name], binding.after, binding.token.start)
        frame.bindings[name] = binding

    def leave(frame: _Frame, end: int) -> None:
        for binding in frame.bindings.values():
            settle(binding, end)
        frame.bindings.clear()

    commands = theory.commands
    for block in theory.goal_blocks():
        stack = [_Frame()]
        for step, i in proof_steps(commands, block.statement, block.stop):
            command = commands[i]
            names = _names(command, list(significant(command.tokens(theory.tokens))))
            if step == "open":
                after = theory.end(command)
                stack.append(_Frame(pending=[_Binding(t, command.name, after) for t in names]))
            elif step == "close":
                frame = stack.pop()
                leave(frame, theory.end(command))
                for binding in frame.pending:
                    binding.after = theory.end(command)
                    binding.anonymous = _chains(theory, i + 1)
                    bind(stack[-1], binding)
            elif step == "next":
                leave(stack[-1], theory.start(command))
            else:
                for token in names:
                    binding = _Binding(token, command.name, theory.end(command))
                    binding.anonymous = _chains(theory, i + 1)
                    bind(stack[-1], binding)
        end = theory.end(commands[block.stop - 1])
        while stack:  # an unfinished proof
            leave(stack.pop(), end)
    return findings
