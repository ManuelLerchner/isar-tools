"""``notation`` group: a constant written out where it has a short form.

A project gives a constant a short form in five ways, and once it has, every
later term should use it:

- a mixfix on its declaration (``definition``, ``fun``, ``consts``, a class or
  locale parameter, a record field, ...): ``f x`` should be written in that
  mixfix;
- a ``notation f (mixfix)`` command, likewise (``notation (input)`` counts,
  other print modes do not);
- ``adhoc_overloading g == f``: ``f x`` should be written ``g x``. An
  instance that is a term (``"lift f"``) is matched as that token sequence.
  Not where no type resolves ``g``: in an attribute instantiation
  (``[where x = "f"]``, ``[of "f"]``), as a bracketed argument
  (``map (f x)``), or, for a class parameter ``f``, inside an
  ``instantiation`` of its class or a subclass, where ``f`` has no variant at
  the instance type yet;
- ``syntax`` and ``translations``: a rule ``"lhs" == "CONST f x y"`` (or
  ``=>``) whose left side applies a syntax constant with a mixfix to the
  variables ``x y`` in any order, in that mixfix or as ``_f y x``, gives
  ``f`` the mixfix with its arguments in the order of the left side. Rules
  with other patterns are not followed, and ``syntax (output)`` gives no short
  form;
- any of these inside ``bundle B begin ... end``: the short form holds where
  ``B`` is open, by ``unbundle B`` (until ``unbundle no B``), ``open_bundle``,
  ``includes B``, ``including B``, or a bundle that unbundles ``B``.

``spelled-out-abbreviation``: a term that is the right-hand side of an
``abbreviation``, its variables matching any argument, should be written as
the abbreviation. Not followed: an alias of one token, a right-hand side that
starts with a variable, and ``c x \\<equiv> f x``, which only narrows the type
of ``f``. A right-hand side with an operator outside brackets matches only a
whole term (bracketed, between separators, or the whole string), since
precedence may split it otherwise. An abbreviation declared in an anonymous
block holds only there, and one from an included session (``-d``) not at all:
it may fix types the project's terms do not have.

A short form holds after the command that introduces it, in its theory and in
every theory importing it. Inside a ``locale``, ``class``, or ``context NAME``
block (or after ``(in NAME)``) it holds in that locale and the locales
extending it; inside an anonymous block, only there. A locale's or class's own
parameters hold already in its header; any other declaration may spell itself
out in its own defining equations.

``ambiguous-notation``: a short form whose notation has the delimiters and
argument slots of another constant's short form that holds where it is
declared, in the same print mode. Isabelle then has two productions for the
notation and reports terms that use it as ambiguous, often far from the
declarations. Overloaded constants share their generic's notation and do not
count. The notation of a parameter of a parent locale does not count either:
an instance that renames the parameter drops its mixfix.

Terms are read lexically, as for ``locales``: the strings and cartouches of
formal commands, without document text, comments, ML, syntax commands, mixfix
annotations, and types after ``::``. Names bound in the term, or fixed by
``fixes``, ``for``, ``fix``, ``obtain``, ``define``, or ``case (C x)`` in the
command, its goal, or its block, are variables. A mixfix needs its arguments,
so a name is reported only when an argument follows it; an infix also has the
unapplied form ``(op)`` and is always reported. Qualified names
(``T.f``) are not followed.

``no_notation f (mixfix)`` ends the short form of ``f`` with that mixfix and
print mode, ``no_adhoc_overloading g == f`` that of ``f`` as ``g``, and
``no_translations`` that of its rules (``no_syntax`` is not followed). The
removal is scoped like ``notation``: in its theory and the theories importing
it, its locale, its anonymous block, or where its bundle is open. It ends only
short forms introduced before it; another short form of the same constant
still holds.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

from isar_tools.checks.findings import Edit, Finding, Fix
from isar_tools.checks.locales import bound_names, term_text
from isar_tools.checks.terms import (
    CLOSERS,
    OPENERS,
    TEXTS,
    argument_end,
    arguments,
    atom,
    delimited,
    has_operator,
    heads,
    match,
    spelling,
    term_tokens,
)
from isar_tools.project.hierarchy import bracket_group, declarations, parse_mixfix
from isar_tools.project.model import Project
from isar_tools.project.names import Entity, entities
from isar_tools.project.names import source as statement_source
from isar_tools.project.notation import (
    INFIX,
    NotationError,
    Syntax,
    Translation,
    expansion,
    fill,
    syntax_entries,
    template,
    translation,
    translation_rules,
)
from isar_tools.project.workspace import SourceFile
from isar_tools.source.files import read_lenient
from isar_tools.source.keywords import DOCUMENT, CommandKind
from isar_tools.source.lexer import IGNORABLE, Kind, Token, tokenize
from isar_tools.source.symbols import encode
from isar_tools.source.theory import Command, Theory, parse_theory, significant, unquote

CODE = "spelled-out-notation"
ABBREVIATION_CODE = "spelled-out-abbreviation"
AMBIGUOUS_CODE = "ambiguous-notation"

# Commands whose strings and cartouches are no terms of the theory.
_NOTEXTS = frozenset(
    {
        "setup",
        "local_setup",
        "attribute_setup",
        "method_setup",
        "simproc_setup",
        "declaration",
        "syntax_declaration",
        "parse_ast_translation",
        "parse_translation",
        "print_translation",
        "typed_print_translation",
        "print_ast_translation",
        "oracle",
        "syntax",
        "no_syntax",
        "translations",
        "no_translations",
        "notation",
        "no_notation",
        "type_notation",
        "no_type_notation",
        "adhoc_overloading",
        "no_adhoc_overloading",
        "code_printing",
        "code_reserved",
        "code_identifier",
        "export_code",
    }
)
# A string after one of these is a mixfix, a type, or a target, not a term.
_NOT_TERM_AFTER = frozenset({"(", "::", "in", "binder", *INFIX})
# Elements that fix variables, and the words that end the variables.
_FIXING = frozenset({"fixes", "for", "fix", "obtain", "obtains", "define"})
_FIXED_END = frozenset(
    {"where", "assumes", "shows", "obtains", "if", "when", "begin", "defines", "notes"}
)
_INCLUDING = frozenset({"includes", "including"})


@dataclass(frozen=True)
class Scope:
    kind: str  # "global", "locale", "block", or "bundle"
    name: str = ""  # the locale or bundle; for a block, its command index


@dataclass(frozen=True)
class ShortForm:
    pattern: tuple[str, ...]  # the written-out term, as tokens with ASCII symbols
    advice: str  # what to write instead
    # Arguments a use needs before the short form can replace it; 0 for one
    # that also has an unapplied form: an infix `(op)`, a notation without
    # slots.
    arity: int
    scope: Scope
    path: Path
    after: int  # index of the command that introduces it
    home: bool = False  # holds inside that command too: a locale's own parameters
    variables: frozenset[str] = frozenset()  # pattern items that match any argument
    code: str = CODE
    # The pattern has an operator outside brackets: a match must be a whole
    # term, or precedence may split it (`a \<and> b` in `a \<and> b \<and> c`).
    whole: bool = False
    # An adhoc_overloading instance: Isabelle resolves the generic name by type.
    overloaded: bool = False
    # What to write: the notation with `_` slots, the generic name, or the
    # abbreviation, applied to `parameters` in the order its left side has them.
    short: str = ""
    parameters: tuple[str, ...] = ()
    mode: str = ""  # "input" for `notation (input)`
    # The `_` slots of `short` that take an argument without its brackets, and
    # those that take only a name or a bracketed term.
    bare: frozenset[int] = frozenset()
    tight: frozenset[int] = frozenset()
    # The argument each slot of `short` takes, if not the slots in order: a
    # translation may reorder them.
    order: tuple[int, ...] = ()

    @property
    def applied(self) -> bool:
        """Whether a use has to head an application: a mixfix with slots, or
        a pattern that is an application itself."""
        return self.arity > 0 or len(self.pattern) > 1


@dataclass(frozen=True)
class _Context:
    """What holds at a command."""

    locale: str  # its target or innermost named block; "" if none
    blocks: frozenset[int]  # the command indices of the blocks around it
    bundles: frozenset[str]  # open bundles, before following unbundle chains
    variables: frozenset[str]
    terms: bool  # its strings and cartouches are terms that are checked
    classes: frozenset[str] = frozenset()  # of the instantiations around it


_NO_CONTEXT = _Context("", frozenset(), frozenset(), frozenset(), False)


@dataclass
class _Block:
    index: int
    locale: str = ""
    bundle: str = ""  # the bundle whose body this is
    opened: set[str] = field(default_factory=set[str])
    variables: frozenset[str] = frozenset()
    classes: frozenset[str] = frozenset()  # an instantiation's


@dataclass
class _Analysis:
    theory: Theory
    contexts: list[_Context]
    opened: frozenset[str]  # bundles open at the end, at theory level
    forms: list[ShortForm]
    # What `no_notation` and `no_adhoc_overloading` remove, as the short forms
    # they end.
    removals: list[ShortForm]
    includes: dict[str, set[str]]  # bundle -> the bundles it unbundles
    syntax: dict[str, Syntax]  # syntax constants declared here or in an import


def _tokens(theory: Theory, command: Command) -> list[Token]:
    """The tokens of ``command`` from its keyword, after ``private``."""
    toks = list(significant(command.tokens(theory.tokens)))
    while toks and toks[0].text != command.name:
        toks.pop(0)
    return toks


def _words_after(args: list[Token], keywords: frozenset[str]) -> Iterator[str]:
    """The names following any of ``keywords``: ``unbundle a b``."""
    for i, tok in enumerate(args):
        if tok.text in keywords:
            for name in args[i + 1 :]:
                if name.kind is not Kind.WORD or name.text in _FIXED_END | keywords:
                    break
                yield name.text


def _bundle_changes(args: list[Token]) -> tuple[set[str], set[str]]:
    """Bundles ``unbundle a no b`` opens and closes."""
    opened: set[str] = set()
    closed: set[str] = set()
    target = opened
    for tok in (t for t in args if t.kind is Kind.WORD):
        if tok.text == "no":
            target = closed
        else:
            target.add(tok.text)
    return opened, closed


def _variables(toks: list[Token]) -> set[str]:
    """Variables the command ``toks`` fixes: ``fix x :: T and y``, ``for x``,
    ``case (C x y)``; not a parameter with a mixfix, which is a short form."""
    names: set[str] = set()
    for i, tok in enumerate(toks):
        if tok.text == "case" and i + 2 < len(toks) and toks[i + 1].text == "(":
            group, _ = bracket_group(toks, i + 1)
            names.update(t.text for t in group[2:] if t.kind is Kind.WORD)
        if tok.text not in _FIXING:
            continue
        entry: list[str] = []
        j = i + 1
        while j < len(toks):
            t = toks[j]
            if t.text == "::":
                j += 2
            elif t.text == "(" and entry:  # a mixfix ends the entry
                entry = []
                j = bracket_group(toks, j)[1]
            elif t.kind is not Kind.WORD or t.text in _FIXED_END | _FIXING:
                break
            else:
                if t.text == "and":
                    names.update(entry)
                    entry = []
                else:
                    entry.append(t.text)
                j += 1
        names.update(entry)
    return names


def _target(args: list[Token]) -> str:
    if len(args) >= 4 and args[0].text == "(" and args[1].text == "in" and args[3].text == ")":
        return unquote(args[2])
    return ""


def _instantiated(args: list[Token]) -> frozenset[str]:
    """The classes of ``instantiation t and u :: (type) c begin``; a sort
    ``"{c, d}"`` names several."""
    at = next((i for i, t in enumerate(args) if t.text == "::"), len(args))
    classes: set[str] = set()
    i = at + 1
    while i < len(args) and args[i].text != "begin":
        if args[i].text == "(":  # the arity's argument sorts
            i = bracket_group(args, i)[1]
            continue
        classes.update(re.findall(r"[A-Za-z][\w.']*", unquote(args[i])))
        i += 1
    return frozenset(classes)


def _scope(stack: list[_Block]) -> Scope:
    if not stack:
        return Scope("global")
    inner = stack[-1]
    if inner.bundle:
        return Scope("bundle", inner.bundle)
    if inner.locale:
        return Scope("locale", inner.locale)
    return Scope("block", str(inner.index))


def _split_and(args: list[Token]) -> list[list[Token]]:
    parts: list[list[Token]] = [[]]
    depth = 0
    for tok in args:
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(tok.text, 0)
        if depth == 0 and tok.kind is Kind.WORD and tok.text == "and":
            parts.append([])
        else:
            parts[-1].append(tok)
    return [p for p in parts if p]


def _pattern(text: str) -> tuple[str, ...]:
    return tuple(encode(t.text) for t in tokenize(text) if t.kind not in IGNORABLE)


_Slots = tuple[frozenset[int], frozenset[int]]
_NO_SLOTS: _Slots = (frozenset(), frozenset())


def _shown(mixfix: str, notation: str) -> tuple[str, int, _Slots] | None:
    """The notation a mixfix writes, its arity, and its bare and tight slots;
    None if it has no notation to suggest."""
    try:
        written = template(mixfix, notation)
        infix = mixfix.partition(" ")[0] in INFIX
        # `'_` quotes the underscore: it is no slot.
        arity = 0 if infix else len(re.findall(r"(?<!')_", written))
        slots = _slots(mixfix, written, arity) if arity else _NO_SLOTS
        return (written, arity, slots) if written else None
    except NotationError:
        return None


def _slots(mixfix: str, written: str, arity: int) -> _Slots:
    """The slots of ``written`` between two delimiters whose priority is 0,
    which a term fills without brackets, as in ``\\<lbrakk>_\\<rbrakk>``; and
    the slots of priority 1000, which take a name or a bracketed term."""
    toks = [t for t in tokenize(mixfix) if t.kind not in IGNORABLE]
    at = next((i for i, t in enumerate(toks) if t.kind in (Kind.STRING, Kind.CARTOUCHE)), 0)
    listed: list[int] = []
    if at + 1 < len(toks) and toks[at + 1].text == "[":
        listed = [int(t.text) for t in bracket_group(toks, at + 1)[0] if t.text.isdigit()]
    priorities = [*listed, *[0] * arity][:arity]  # unlisted arguments have priority 0
    marked = fill(written, "", [f"\0{k}\0" for k in range(arity)]).replace(" ", "")
    pieces = marked.split("\0")  # delimiters at even indices, slots at odd ones
    bare = (k for k in range(arity) if priorities[k] == 0 and pieces[2 * k] and pieces[2 * k + 2])
    return frozenset(bare), frozenset(k for k in range(arity) if priorities[k] >= 1000)


def _in_bundle(scope: Scope) -> str:
    return f" (bundle {scope.name})" if scope.kind == "bundle" else ""


def _notations(args: list[Token], scope: Scope, path: Path, index: int) -> Iterator[ShortForm]:
    """``notation (input) f (mixfix) and g (mixfix)``, or what the same
    arguments of ``no_notation`` remove."""
    mode = ""
    if len(args) > 2 and args[0].text == "(" and args[2].text == ")":
        if args[1].text != "input":
            return  # a print mode: the input is still written out
        mode = "input"
        args = args[3:]
    for part in _split_and(args):
        if len(part) < 2 or part[0].kind not in (Kind.WORD, Kind.STRING) or part[1].text != "(":
            continue
        shown = _shown(*parse_mixfix(bracket_group(part, 1)[0]))
        if shown is not None:
            name = unquote(part[0]).rpartition(".")[2]
            advice = f"its notation is {shown[0]}{_in_bundle(scope)}"
            yield ShortForm(
                (encode(name),),
                advice,
                shown[1],
                scope,
                path,
                index,
                short=shown[0],
                mode=mode,
                bare=shown[2][0],
                tight=shown[2][1],
            )


def _overloadings(args: list[Token], scope: Scope, path: Path, index: int) -> Iterator[ShortForm]:
    """``adhoc_overloading g == f "t u" and h == k``, or what the same
    arguments of ``no_adhoc_overloading`` remove; the ``==`` is optional."""
    for part in _split_and(args):
        generic = unquote(part[0]).rpartition(".")[2]
        advice = f"it is overloaded as {generic}{_in_bundle(scope)}"
        instances = [t for t in part[1:] if t.kind in (Kind.WORD, Kind.STRING, Kind.CARTOUCHE)]
        for pattern in filter(None, (_pattern(unquote(t)) for t in instances)):
            yield ShortForm(pattern, advice, 1, scope, path, index, overloaded=True, short=generic)


def _entity_scope(e: Entity) -> Scope:
    parameter = e.member and e.command in ("fixes", "for")
    if parameter and e.scope.endswith("_class"):
        return Scope("global")  # a class parameter is a global constant
    if e.scope and (parameter or not e.member):
        return Scope("locale", e.scope)
    return Scope("global")


def _abbreviation(theory: Theory, e: Entity, index: int, scope: Scope) -> ShortForm | None:
    r"""``abbreviation c where "c x \<equiv> f x (g x)"``: the right-hand side as
    a pattern with the variables of the left. Not reported: an alias of one
    token, a pattern that starts with a variable, and ``c x \<equiv> f x``,
    which only gives ``f`` a narrower type."""
    try:
        lhs, rhs = expansion(statement_source(theory, e, statement=True))
    except NotationError:
        return None
    parameters = [t.text for t in term_tokens(lhs) if t.kind is Kind.WORD and t.text != e.name]
    variables = frozenset(parameters)
    toks = term_tokens(rhs)
    pattern = tuple(spelling(toks))
    if len(pattern) < 2 or pattern[0] in variables or list(pattern[1:]) == parameters:
        return None
    advice = f"it is the abbreviation {e.name}"
    return ShortForm(
        pattern,
        advice,
        0,
        scope,
        e.path,
        index,
        variables=variables,
        code=ABBREVIATION_CODE,
        whole=has_operator(toks),
        short=e.name,
        parameters=tuple(parameters),
    )


def _declared_forms(theory: Theory, path: Path, blocks: list[Scope]) -> Iterator[ShortForm]:
    """Short forms from the mixfix of a declaration, and abbreviations.
    ``blocks`` is the scope of the block around each command."""
    name = theory.header.name.text if theory.header else path.stem
    for e in entities(theory, name, path):
        if e.kind != "constant" or e.mode == "output":
            continue
        index = e.command_index
        if e.command == "abbreviation":
            # Inside an anonymous block, the abbreviation is generalized
            # over the block's parameters when it leaves it.
            block = blocks[index]
            scope = block if block.kind == "block" else _entity_scope(e)
            if form := _abbreviation(theory, e, index, scope):
                yield form
        shown = _shown(e.mixfix, e.notation)
        if shown is None:
            continue
        parameter = e.member and e.command in ("fixes", "for")
        advice = f"its notation is {shown[0]}"
        scope = _entity_scope(e)
        yield ShortForm(
            (encode(e.name),),
            advice,
            shown[1],
            scope,
            path,
            index,
            parameter,
            short=shown[0],
            bare=shown[2][0],
            tight=shown[2][1],
        )


def _opens_block(command: Command, args: list[Token]) -> bool:
    return command.kind is CommandKind.THY_DECL_BLOCK and bool(args) and args[-1].text == "begin"


def _translated(t: Translation, scope: Scope, path: Path, index: int) -> ShortForm | None:
    """The short form a translation rule gives its constant; None if the rule
    only prints or its syntax is for another print mode."""
    if not t.parse or t.syntax.mode not in ("", "input"):
        return None
    n = len(t.parameters)
    slots = _slots(t.syntax.mixfix, t.template, n)
    written = f"{t.written(list(t.parameters))} for {' '.join([t.constant, *t.parameters])}"
    return ShortForm(
        (encode(t.constant),),
        f"its notation is {written}{_in_bundle(scope)}",
        n,
        scope,
        path,
        index,
        short=t.template,
        mode=t.syntax.mode,
        bare=slots[0],
        tight=slots[1],
        order=t.order,
    )


def _analyze(
    path: Path, theory: Theory, opened_before: frozenset[str], syntax: dict[str, Syntax]
) -> _Analysis:
    """Contexts and short forms of ``theory``, whose imports leave the bundles
    ``opened_before`` open and declare the syntax constants ``syntax``, which
    collects those of ``theory`` too."""
    goal: dict[int, tuple[set[str], set[str]]] = {}
    for block in theory.goal_blocks():
        bundles: set[str] = set()
        variables: set[str] = set()
        for k in range(block.statement, block.stop):
            toks = _tokens(theory, theory.commands[k])
            bundles.update(_words_after(toks, _INCLUDING))
            variables |= _variables(toks)
        goal.update(dict.fromkeys(range(block.statement, block.stop), (bundles, variables)))
    stack: list[_Block] = []
    opened = set(opened_before)
    contexts: list[_Context] = []
    blocks: list[Scope] = []
    forms: list[ShortForm] = []
    removals: list[ShortForm] = []
    includes: dict[str, set[str]] = {}
    for i, command in enumerate(theory.commands):
        toks = _tokens(theory, command)
        args = toks[1:]
        if command.kind is CommandKind.THY_END:
            if stack:
                stack.pop()
            contexts.append(_NO_CONTEXT)
            blocks.append(Scope("global"))
            continue
        bundle = next((b.bundle for b in reversed(stack) if b.bundle), "")
        bundles, variables = goal.get(i) or (
            set(_words_after(toks, _INCLUDING)),
            _variables(toks),
        )
        level = opened.union(*(b.opened for b in stack))
        contexts.append(
            _Context(
                _target(args) or next((b.locale for b in reversed(stack) if b.locale), ""),
                frozenset(b.index for b in stack),
                frozenset(level | bundles),
                frozenset(variables).union(*(b.variables for b in stack)),
                not bundle
                and command.kind not in DOCUMENT
                and command.name not in _NOTEXTS
                and "ML" not in command.name,
                frozenset[str]().union(*(b.classes for b in stack)),
            )
        )
        scope = _scope(stack)
        blocks.append(scope)
        if command.name == "notation":
            forms += _notations(args, scope, path, i)
        elif command.name == "no_notation":
            removals += _notations(args, scope, path, i)
        elif command.name == "adhoc_overloading":
            forms += _overloadings(args, scope, path, i)
        elif command.name == "no_adhoc_overloading":
            removals += _overloadings(args, scope, path, i)
        elif command.name == "syntax":
            syntax.update((s.name, s) for s in syntax_entries(args))
        elif command.name in ("translations", "no_translations"):
            rules = (translation(*rule, syntax) for rule in translation_rules(args))
            added = [f for t in rules if t and (f := _translated(t, scope, path, i))]
            (forms if command.name == "translations" else removals).extend(added)
        elif command.name == "unbundle":
            added, removed = _bundle_changes(args)
            if bundle:
                includes.setdefault(bundle, set()).update(added)
            else:
                target = stack[-1].opened if stack else opened
                target |= added
                target -= removed
        elif command.name in ("bundle", "open_bundle") and len(args) > 2 and args[1].text == "=":
            names = [t.text for t in args[2:] if t.kind is Kind.WORD]
            includes.setdefault(unquote(args[0]), set()).update(names)
        if command.name == "open_bundle" and args:
            (stack[-1].opened if stack else opened).add(unquote(args[0]))
        if _opens_block(command, args):
            block = _Block(i, variables=frozenset(_variables(toks)))
            named = command.name == "context" and len(args) == 2
            if command.name in ("locale", "class") or named:
                block.locale = unquote(args[0])
            elif command.name in ("bundle", "open_bundle"):
                block.bundle = unquote(args[0])
            elif command.name == "instantiation":
                block.classes = _instantiated(args)
            elif command.name == "context":
                block.opened.update(_words_after(args, _INCLUDING))
            stack.append(block)
    forms += _declared_forms(theory, path, blocks)
    return _Analysis(theory, contexts, frozenset(opened), forms, removals, includes, syntax)


def _field_name(toks: list[Token], i: int) -> bool:
    r"""Whether ``toks[i]`` names a record field to update or construct:
    ``r\<lparr>f := x\<rparr>``, ``\<lparr>f = x, g = y\<rparr>``."""
    after = "".join(t.text for t in toks[i + 1 : i + 3])
    before = encode(toks[i - 1].text) if i else ""
    # `:=` lexes as `:` and `=`; `(|` as `(` and `|`.
    return after == ":=" or (after[:1] == "=" and before in ("\\<lparr>", "|", ","))


class _Checker:
    def __init__(self, project: Project, allow: frozenset[str]) -> None:
        self.project = project
        self.allow = allow
        self.analyses: dict[Path, _Analysis | None] = {}
        self.parents: dict[str, set[str]] = {}
        self.parameters: dict[str, set[str]] = {}  # class -> its own parameters
        self._visible: dict[Path, set[Path]] = {}
        self._ancestors: dict[str, set[str]] = {}

    def analysis(self, path: Path) -> _Analysis | None:
        if path in self.analyses:
            return self.analyses[path]
        self.analyses[path] = None  # an import cycle stops here
        session = self.project.session_of(path)
        header = self.project.header(path)
        opened: set[str] = set()
        syntax: dict[str, Syntax] = {}
        for imp in header.imports if header else ():
            target = self.project.resolve_import(path, session, imp.text)
            found = self.analysis(target) if target is not None else None
            if found is not None:
                opened |= found.opened
                syntax.update(found.syntax)
        theory = parse_theory(read_lenient(path), self.project.keywords_for(path))
        for decl in declarations(theory, path):
            extra = decl.sorts if decl.kind == "class" else []
            self.parents.setdefault(decl.name, set()).update(decl.parents, extra)
            if decl.kind == "class":
                self.parameters.setdefault(decl.name, set()).update(p.name for p in decl.fixes)
        result = self.analyses[path] = _analyze(path, theory, frozenset(opened), syntax)
        return result

    def visible(self, path: Path) -> set[Path]:
        if path not in self._visible:
            session = self.project.session_of(path)
            self._visible[path] = set(self.project.closure([path], session))
        return self._visible[path]

    def ancestors(self, locale: str) -> set[str]:
        """``locale`` and every locale or class it extends."""
        if locale not in self._ancestors:
            seen: set[str] = set()
            stack = [locale]
            while stack:
                name = stack.pop()
                if name and name not in seen:
                    seen.add(name)
                    stack += self.parents.get(name, ())
            self._ancestors[locale] = seen
        return self._ancestors[locale]


def _expand(bundles: Iterable[str], includes: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(bundles)
    while stack:
        name = stack.pop()
        if name not in seen:
            seen.add(name)
            stack += includes.get(name, ())
    return seen


def _active(
    form: ShortForm,
    path: Path,
    index: int,
    context: _Context,
    bundles: set[str],
    checker: _Checker,
) -> bool:
    if form.overloaded and context.classes and len(form.pattern) == 1:
        classes = set[str]().union(*map(checker.ancestors, context.classes))
        if any(form.pattern[0] in checker.parameters.get(c, ()) for c in classes):
            return False  # the class parameter has no variant at the instance type
    if form.path == path and index <= form.after:
        return form.home and index == form.after
    if form.path != path and form.path not in checker.visible(path):
        return False
    kind, name = form.scope.kind, form.scope.name
    if kind == "locale":
        return name in checker.ancestors(context.locale)
    if kind == "block":
        return form.path == path and int(name) in context.blocks
    if kind == "bundle":
        return name in bundles
    return True


def _ends(removal: ShortForm, form: ShortForm, checker: _Checker) -> bool:
    """Whether ``removal`` removes ``form``: the same constant and short form,
    in the same print mode, after it."""
    if (removal.overloaded, removal.mode) != (form.overloaded, form.mode) or form.code != CODE:
        return False
    if encode(removal.short) != encode(form.short):
        return False
    if removal.path == form.path:
        return removal.after > form.after
    return form.path in checker.visible(removal.path)


def _holds(
    form: ShortForm,
    path: Path,
    index: int,
    context: _Context,
    bundles: set[str],
    checker: _Checker,
    removals: dict[tuple[str, ...], list[ShortForm]],
) -> bool:
    """Whether ``form`` holds at command ``index`` of ``path``: it is active
    there and no removal of it is."""
    return _active(form, path, index, context, bundles, checker) and not any(
        _ends(r, form, checker) and _active(r, path, index, context, bundles, checker)
        for r in removals.get(form.pattern, ())
    )


def _delimiters(form: ShortForm) -> tuple[str, ...] | None:
    """What a parser sees of ``form``'s notation: the delimiters around and
    between its argument slots, without layout; None for a form that is no
    mixfix (an overloading, an abbreviation)."""
    if form.code != CODE or form.overloaded:
        return None
    slots = len(re.findall(r"(?<!')_", form.short))
    try:
        marked = fill(form.short, "", ["\0"] * slots)
    except NotationError:  # a structure index
        return None
    return tuple(encode(marked).replace(" ", "").split("\0"))


def _inherited(form: ShortForm, context: _Context) -> bool:
    """Whether ``form`` is the notation of a parameter of a locale that
    ``context`` only extends: an instance that renames the parameter drops
    its mixfix, and the parent expression is not read."""
    return form.home and form.scope.kind == "locale" and form.scope.name != context.locale


def _declared_at(theory: Theory, form: ShortForm) -> int:
    """The offset of the constant's name in the command introducing ``form``."""
    command = theory.commands[form.after]
    toks = list(significant(command.tokens(theory.tokens)))
    name = form.pattern[0]
    return next((t.start for t in toks if encode(unquote(t)) == name), toks[0].start)


def _ambiguities(
    path: Path,
    found: _Analysis,
    by_delimiters: dict[tuple[str, ...], list[ShortForm]],
    removals: dict[tuple[str, ...], list[ShortForm]],
    includes: dict[str, set[str]],
    checker: _Checker,
) -> Iterator[Finding]:
    """Short forms ``path`` introduces with the delimiters of another short
    form that holds there: Isabelle has two productions for them."""
    for form in sorted((f for f in found.forms if f.path == path), key=lambda f: f.after):
        delimiters = _delimiters(form)
        if delimiters is None or form.pattern[0] in checker.allow:
            continue
        context = found.contexts[form.after]
        if form.scope.kind == "locale":  # a parameter's notation lives in its locale
            context = replace(context, locale=form.scope.name)
        bundles = _expand(context.bundles, includes)
        rivals = sorted(
            (
                other
                for other in by_delimiters.get(delimiters, ())
                if other.pattern != form.pattern
                and other.mode == form.mode
                and not _inherited(other, context)
                and _holds(other, path, form.after, context, bundles, checker, removals)
            ),
            key=lambda other: (other.path == path, str(other.path), other.after),
        )
        if rivals:
            other = rivals[0]
            theirs = checker.analyses[other.path]
            assert theirs is not None  # every form comes from an analysis
            line = theirs.theory.lines.line(_declared_at(theirs.theory, other))
            yield Finding.at(
                path,
                found.theory.lines,
                _declared_at(found.theory, form),
                AMBIGUOUS_CODE,
                f"{form.pattern[0]} has the notation {form.short} of {other.pattern[0]} "
                f"({other.path.name}:{line}); terms using it are ambiguous",
            )


@dataclass
class _Index:
    """The short forms of a project, ready to look up."""

    checker: _Checker
    includes: dict[str, set[str]]  # bundle -> the bundles it unbundles
    by_first: dict[str, list[ShortForm]]  # by the first token of the pattern
    by_delimiters: dict[tuple[str, ...], list[ShortForm]]  # mixfixes, by `_delimiters`
    removals: dict[tuple[str, ...], list[ShortForm]]  # by pattern

    def holds(self, form: ShortForm, path: Path, index: int) -> bool:
        """Whether ``form`` holds at command ``index`` of ``path``."""
        found = self.checker.analyses[path]
        assert found is not None  # every checked path is analyzed
        context = found.contexts[index]
        bundles = _expand(context.bundles, self.includes)
        return _holds(form, path, index, context, bundles, self.checker, self.removals)


def _index(project: Project, paths: list[Path], allow: frozenset[str]) -> _Index:
    """The short forms of ``project`` and the theories ``paths`` reach."""
    checker = _Checker(project, allow)
    universe = list(dict.fromkeys(project.closure([*paths, *project.theory_files()], None)))
    for path in universe:
        checker.analysis(path)
    index = _Index(checker, {}, {}, {}, {})
    for found in (a for a in checker.analyses.values() if a is not None):
        for bundle, names in found.includes.items():
            index.includes.setdefault(bundle, set()).update(names)
        for removal in found.removals:
            index.removals.setdefault(removal.pattern, []).append(removal)
        for form in found.forms:
            if (delimiters := _delimiters(form)) is not None:
                index.by_delimiters.setdefault(delimiters, []).append(form)
            session = project.session_of(form.path)
            # An included theory's abbreviation may fix types the project's own
            # terms do not have, and is no part of its vocabulary.
            foreign = session is not None and session.external
            if foreign and form.code == ABBREVIATION_CODE:
                continue
            if " ".join(form.pattern) not in allow:
                index.by_first.setdefault(form.pattern[0], []).append(form)
    return index


def _by_project(sources: Iterable[SourceFile]) -> Iterator[tuple[Project, list[Path]]]:
    by_project: dict[int, tuple[Project, list[Path]]] = {}
    for source in sources:
        by_project.setdefault(id(source.project), (source.project, []))[1].append(source.path)
    yield from by_project.values()


def check_notation(sources: Iterable[SourceFile], *, allow: Iterable[str] = ()) -> list[Finding]:
    """Terms in ``sources`` that write out a constant with a short form, and
    short forms ``sources`` declare with the delimiters of another."""
    findings: list[Finding] = []
    for project, paths in _by_project(sources):
        index = _index(project, paths, frozenset(allow))
        checker = index.checker
        for path in paths:
            found = checker.analyses[path]
            assert found is not None  # set once the import cycle guard is left
            findings += _check(path, found, index.by_first, index.removals, index.includes, checker)
            findings += _ambiguities(
                path, found, index.by_delimiters, index.removals, index.includes, checker
            )
    return findings


def _passed_partially(toks: list[Token], start: int, end: int) -> bool:
    """Whether the application at ``toks[start:end]`` and its one argument form a
    bracket group passed as an argument, as in ``map f (g x)``: its type is a
    function the context does not fix."""
    stop = argument_end(toks, end)
    return (
        start > 1
        and toks[start - 1].text == "("
        and stop < len(toks)
        and toks[stop].text == ")"
        and not heads(toks, start - 1)
    )


def _wrap(toks: list[Token], start: int, stop: int, term: str) -> str:
    return term if delimited(toks, start, stop) else f"({term})"


def _args_after(toks: list[Token], text: str, i: int, n: int) -> tuple[list[str], int]:
    """The source of the ``n`` arguments from ``toks[i]``, and the index after them."""
    out: list[str] = []
    for _ in range(n):
        stop = argument_end(toks, i)
        out.append(text[toks[i].start : toks[stop - 1].end])
        i = stop
    return out, i


def _unbracketed(toks: list[Token], text: str, i: int) -> str:
    """The source of the argument at ``toks[i]`` without the parentheses around
    it; a tuple ``(a, b)`` or ``()`` keeps them."""
    stop = argument_end(toks, i)
    source = text[toks[i].start : toks[stop - 1].end]
    if toks[i].text != "(" or stop - i < 3:
        return source
    depth = 0
    for tok in toks[i + 1 : stop - 1]:
        depth += (encode(tok.text) in OPENERS) - (encode(tok.text) in CLOSERS)
        if depth == 0 and tok.text == ",":
            return source
    return text[toks[i + 1].start : toks[stop - 2].end]


def _rewrite(form: ShortForm, toks: list[Token], text: str, j: int, end: int) -> Edit | None:
    """The edit of ``text`` that writes the match ``toks[j:end]`` (with the
    arguments the form takes) as its short form."""
    at, after = toks[j].start, toks[end - 1].end
    if form.code == ABBREVIATION_CODE:
        source: dict[str, str] = {}
        i = j
        for item in form.pattern:
            if item in form.variables:
                stop = argument_end(toks, i)
                source.setdefault(item, text[toks[i].start : toks[stop - 1].end])
                i = stop
            else:
                i += 1
        if not set(form.parameters) <= source.keys():
            return None
        term = " ".join([form.short, *(source[v] for v in form.parameters)])
        return Edit(at, after, _wrap(toks, j, end, term) if form.parameters else term)
    if form.overloaded:
        return Edit(at, after, form.short)
    notation = form.short
    infix = notation.startswith("_ ") and notation.endswith(" _")
    if form.arity == 0 and not infix:
        return Edit(at, after, notation)  # a constant written without slots
    if infix:
        op = notation[2:-2]
        if arguments(toks, end) < 2 or not heads(toks, j):
            return Edit(at, after, f"({op})")
        args, stop = _args_after(toks, text, end, 2)
        left, right = (args[k] for k in form.order or (0, 1))
        return Edit(at, toks[stop - 1].end, _wrap(toks, j, stop, f"{left} {op} {right}"))
    args, stop = _args_after(toks, text, end, form.arity)
    starts = [end]
    for _ in args[:-1]:
        starts.append(argument_end(toks, starts[-1]))
    # Slot `k` takes argument `order[k]`.
    args = [
        _unbracketed(toks, text, starts[a]) if k in form.bare else args[a]
        for k, a in enumerate(form.order or range(len(args)))
    ]
    filled = fill(notation, "", args)  # `_shown` rejected what `fill` cannot do
    # A mixfix with delimiters on both sides (`\<lbrakk>_\<rbrakk>`) reads as one unit.
    closed = not notation.startswith("_") and not notation.endswith("_")
    return Edit(at, toks[stop - 1].end, filled if closed else _wrap(toks, j, stop, filled))


def _term_texts(found: _Analysis) -> Iterator[tuple[int, str, str, int]]:
    """The terms of the theory: the index of their command, the token before
    them, their text, and its offset."""
    theory = found.theory
    for index, command in enumerate(theory.commands):
        if not found.contexts[index].terms:
            continue
        toks = list(significant(command.tokens(theory.tokens)))
        for k, tok in enumerate(toks):
            before = toks[k - 1].text if k else ""
            if tok.kind in TEXTS and before not in _NOT_TERM_AFTER:
                yield (index, before, *term_text(tok))


def _check(
    path: Path,
    found: _Analysis,
    by_first: dict[str, list[ShortForm]],
    removals: dict[tuple[str, ...], list[ShortForm]],
    includes: dict[str, set[str]],
    checker: _Checker,
) -> Iterator[Finding]:
    theory = found.theory

    def holds(form: ShortForm, index: int, context: _Context, bundles: set[str]) -> bool:
        return _holds(form, path, index, context, bundles, checker, removals)

    for index, before, text, start in _term_texts(found):
        context = found.contexts[index]
        bundles = _expand(context.bundles, includes)
        # `[where f = "..."]`, `[of "..."]`: a term with no surrounding type.
        instantiation = before in ("=", "of")
        inner = term_tokens(text)
        spelled = spelling(inner)
        variables = bound_names(inner) | context.variables
        consumed = 0
        for j, t in enumerate(inner):
            if j < consumed or t.kind is not Kind.WORD or t.text in variables:
                continue
            if _field_name(inner, j):
                continue
            best: tuple[ShortForm, int] | None = None
            for form in by_first.get(spelled[j], ()):
                end = match(form.pattern, form.variables, inner, spelled, j)
                if (
                    end is not None
                    and (best is None or end > best[1])
                    and holds(form, index, context, bundles)
                ):
                    best = form, end
            if best is None:
                continue
            form, consumed = best
            if form.applied and not heads(inner, j):
                continue
            if form.whole and not delimited(inner, j, consumed):
                continue
            if form.overloaded and (instantiation or _passed_partially(inner, j, consumed)):
                continue  # the generic name could not be resolved there
            if arguments(inner, consumed) >= form.arity:
                written = " ".join(text[t.start : inner[consumed - 1].end].split())
                edit = _rewrite(form, inner, text, j, consumed)
                fix = None
                if edit is not None:
                    moved = Edit(start + edit.start, start + edit.end, edit.text)
                    fix = Fix((moved,), safe=False)
                yield Finding.at(
                    path,
                    theory.lines,
                    start + t.start,
                    form.code,
                    f"{written} is written out; {form.advice}",
                    fix,
                )


# Rewriting the uses of a constant's former notation (`isar project renotate`).

_SEPARATORS = frozenset({",", ";", "|"})
# Pure's notations that share delimiters with a project's.
_PURE = ("\\<lbrakk>_\\<rbrakk> \\<Longrightarrow> _", "[| _ |] ==> _")
_Items = tuple[str | None, ...]


@cache
def _items(written: str) -> _Items | None:
    """The tokens of the notation ``written``, with None for each argument
    slot; None for a notation ``fill`` cannot write."""
    try:
        marked = fill(written, "", ["\0"] * len(re.findall(r"(?<!')_", written)))
    except NotationError:
        return None
    items: list[str | None] = []
    for k, piece in enumerate(marked.split("\0")):
        items += [None] * bool(k) + spelling(term_tokens(piece))
    return tuple(items)


@dataclass(frozen=True)
class _Use:
    """Tokens ``start:end`` of a term written in a notation."""

    start: int
    end: int
    slots: tuple[tuple[int, int], ...]  # the token range of each argument
    delimiters: int  # how many tokens of the notation it has


def _argument_start(toks: list[Token], spelled: list[str], end: int) -> int | None:
    """The index of the argument that ends before ``toks[end]``."""
    if end == 0:
        return None
    if spelled[end - 1] not in CLOSERS:
        return end - 1 if atom(toks[end - 1]) else None
    depth = 0
    for i in range(end - 1, -1, -1):
        depth += (spelled[i] in CLOSERS) - (spelled[i] in OPENERS)
        if depth == 0:
            return i
    return None


def _slot_end(items: _Items, k: int, spelled: list[str], i: int) -> int | None:
    """The end of the argument in slot ``items[k]`` from ``spelled[i]``: the next
    delimiter outside brackets and outside nested uses of the notation."""
    close = items[k + 1]
    opener = items[k - 1] if k else None
    depth = nested = 0
    for j in range(i, len(spelled)):
        text = spelled[j]
        if text == close and depth == nested == 0:
            return j if j > i else None
        if text in OPENERS:
            depth += 1
        elif text in CLOSERS:
            depth -= 1
        elif text == opener:
            nested += 1
        elif text == close:
            nested -= 1
        if depth < 0:
            return None
    return None


def _uses(
    items: _Items, toks: list[Token], spelled: list[str], strict: bool = True
) -> Iterator[_Use]:
    """The terms of ``toks`` written in the notation ``items``. A slot between
    delimiters holds anything up to the next one; a slot at either end holds
    one argument that takes part in no application. Unless ``strict``, the
    last slot may be followed by more arguments, which it may take."""
    first = next((k for k, item in enumerate(items) if item is not None), None)
    if first is None or None in (items[k] for k in range(first) if k):
        return  # no delimiter, or two slots before the first
    for p in (p for p, text in enumerate(spelled) if text == items[first]):
        slots: list[tuple[int, int]] = []
        start = p
        if first:
            start = _argument_start(toks, spelled, p)
            if start is None or not heads(toks, start):
                continue
            slots.append((start, p))
        i, k = p, first
        while i is not None and k < len(items):
            item = items[k]
            if item is not None:
                i, k = (i + 1, k + 1) if i < len(spelled) and spelled[i] == item else (None, k)
            elif k + 1 == len(items):
                end = argument_end(toks, i)
                ok = end > i and (not strict or arguments(toks, end) == 0)
                slots.append((i, end))
                i, k = (end if ok else None), k + 1
            elif items[k + 1] is None:  # the next slot follows: one argument
                end = argument_end(toks, i)
                slots.append((i, end))
                i, k = (end if end > i else None), k + 1
            else:
                end = _slot_end(items, k, spelled, i)
                slots.append((i, end or i))
                i, k = end, k + 1
        if i is not None:
            yield _Use(start, i, tuple(slots), sum(item is not None for item in items))


@dataclass(frozen=True)
class Renotation:
    """The edits that rewrite uses of a former notation, by file, and the uses
    left as written: file, line, and why."""

    edits: dict[Path, list[Edit]]
    notes: list[tuple[Path, int, str]]


def former(mixfix: str) -> str:
    """The notation of ``mixfix``, as given to ``--from``: an annotation as a
    declaration writes it, with or without its parentheses, or the bare
    notation."""
    toks = list(significant(tokenize(mixfix)))
    if toks and toks[0].text == "(":
        text, notation = parse_mixfix(bracket_group(toks, 0)[0])
    else:
        text = mixfix.strip()
        texts = [unquote(t) for t in toks if t.kind in (Kind.STRING, Kind.CARTOUCHE)]
        notation = texts[0] if texts else text
    if not notation:
        raise NotationError(f"no notation in ({mixfix})")
    return template(text, notation)


def renotate(sources: Iterable[SourceFile], constant: str, old: str) -> Renotation:
    """The edits of ``sources`` that rewrite terms written in ``constant``'s
    former notation ``old`` (a template, as ``former`` reads it) into the
    notation its declaration has now. Several declarations of the name (the
    parameters of different locales) each rewrite the terms where they hold."""
    name = encode(constant.rpartition(".")[2])
    renotation = Renotation({}, [])
    old_items = _items(old)
    if not old_items or old_items == (None,):
        raise NotationError(f'the notation "{old}" is not supported')
    for project, paths in _by_project(sources):
        index = _index(project, paths, frozenset())
        named = [f for forms in index.by_delimiters.values() for f in forms if f.pattern == (name,)]
        current = [f for f in named if _items(f.short) != old_items]
        if not current:
            raise NotationError(f'{constant} has no notation other than "{old}"')
        for path in paths:
            found = index.checker.analyses[path]
            assert found is not None  # set once the import cycle guard is left
            edits = list(_renotate_theory(path, found, index, named, old_items, renotation))
            if edits:
                renotation.edits[path] = edits
    return renotation


def _renotate_theory(
    path: Path,
    found: _Analysis,
    index: _Index,
    named: list[ShortForm],
    old_items: _Items,
    renotation: Renotation,
) -> Iterator[Edit]:
    syntax = [s.notation for s in found.syntax.values() if s.mode != "output"]
    forms = [f for same in index.by_delimiters.values() for f in same]
    held: dict[int, tuple[list[ShortForm], list[_Items]]] = {}  # by command
    for command, _, text, start in _term_texts(found):
        if command not in held:
            # A declaration's own equations already use its notation.
            here = [
                f
                for f in forms
                if (f.path, f.after) == (path, command) or index.holds(f, path, command)
            ]
            # Another constant with the former notation makes a use ambiguous.
            others = [f.short for f in here if f not in named or _items(f.short) != old_items]
            written = {_items(w) for w in [*_PURE, *syntax, *others]}
            productions = [i for i in written if i is not None]
            mine = {f.short: f for f in named if f in here}
            # Where a declaration of the name keeps the former notation, it is no former one.
            stale = any(_items(short) == old_items for short in mine)
            held[command] = [] if stale else list(mine.values()), productions
        targets, productions = held[command]
        if not targets:
            continue  # the constant has no new notation here
        toks = term_tokens(text)
        spelled = spelling(toks)
        uses = list(_uses(old_items, toks, spelled))
        rivals = [u for items in productions for u in _uses(items, toks, spelled, False)]
        new = targets[0]
        new_items = _items(new.short)
        assert new_items is not None  # `_delimiters` read it
        accepted: dict[_Use, int] = {}  # a use and the end of the arguments it takes
        for use in uses:
            if any(
                r.start <= use.start and r.end >= use.end and r.delimiters >= use.delimiters
                for r in rivals
            ):
                continue  # another notation that is at least as long
            line = found.theory.lines.line(start + toks[use.start].start)
            extra = new_items.count(None) - len(use.slots)
            if len(targets) > 1:
                shown = ", ".join(f.short for f in targets)
                renotation.notes.append((path, line, f"it has several notations: {shown}"))
            elif extra > 0 and (not heads(toks, use.start) or arguments(toks, use.end) < extra):
                renotation.notes.append((path, line, f"too few arguments for {new.short}"))
            else:
                end = use.end
                for _ in range(max(extra, 0)):
                    end = argument_end(toks, end)
                accepted[use] = end
        for use, end in _outermost(accepted):
            replacement = _renotated_use(use, end, accepted, new, new_items, toks, spelled, text)
            yield Edit(start + toks[use.start].start, start + toks[end - 1].end, replacement[0])


def _outermost(accepted: dict[_Use, int]) -> list[tuple[_Use, int]]:
    """The uses not inside another, in order."""
    out: list[tuple[_Use, int]] = []
    for use, end in sorted(accepted.items(), key=lambda item: (item[0].start, -item[1])):
        if not out or use.start >= out[-1][1]:
            out.append((use, end))
    return out


def _renotated_range(
    a: int,
    b: int,
    accepted: dict[_Use, int],
    new: ShortForm,
    new_items: _Items,
    toks: list[Token],
    spelled: list[str],
    text: str,
) -> tuple[str, bool]:
    """The text of ``toks[a:b]`` with the uses inside rewritten, and whether
    it is one argument."""
    inside = {u: e for u, e in accepted.items() if a <= u.start and e <= b}
    if (whole := next((u for u, e in inside.items() if (u.start, e) == (a, b)), None)) is not None:
        # The use is the whole argument: the caller brackets it if it must.
        return _renotated_use(whole, b, accepted, new, new_items, toks, spelled, text, False)
    out: list[str] = []
    at = toks[a].start
    for use, end in _outermost(inside):
        out.append(text[at : toks[use.start].start])
        out.append(_renotated_use(use, end, accepted, new, new_items, toks, spelled, text)[0])
        at = toks[end - 1].end
    return "".join(out) + text[at : toks[b - 1].end], argument_end(toks, a) == b


def _renotated_use(
    use: _Use,
    end: int,
    accepted: dict[_Use, int],
    new: ShortForm,
    new_items: _Items,
    toks: list[Token],
    spelled: list[str],
    text: str,
    bracket: bool = True,
) -> tuple[str, bool]:
    """``use`` and the arguments up to ``end`` written in the notation ``new``,
    in brackets where the term around needs them (with ``bracket``), and
    whether that is one argument."""
    ranges = list(use.slots)
    at = use.end
    while at < end:  # the arguments the notation takes beyond the use
        ranges.append((at, argument_end(toks, at)))
        at = ranges[-1][1]
    args = [
        _renotated_range(a, b, accepted, new, new_items, toks, spelled, text) for a, b in ranges
    ]
    written = [arg if single else f"({arg})" for arg, single in args]
    slots = new_items.count(None)
    order = new.order or tuple(range(slots))
    filled = fill(
        new.short, "", [args[a][0] if k in new.bare else written[a] for k, a in enumerate(order)]
    )
    closed = new_items[0] is not None and new_items[-1] is not None
    applied = len(args) > slots  # the notation applied to the remaining arguments
    if applied:
        filled = " ".join([filled if closed else f"({filled})", *written[slots:]])
    elif closed:
        return filled, True
    if not bracket:
        return filled, False
    before = spelled[use.start - 1] if use.start else ""
    after = spelled[end] if end < len(spelled) else ""
    # An open end whose slot takes more than a name could swallow what is next to it.
    left = not applied and new_items[0] is None and 0 not in new.tight
    right = not applied and new_items[-1] is None and slots - 1 not in new.tight
    if (
        not heads(toks, use.start)
        or arguments(toks, end) > 0
        or (left and before not in {"", *OPENERS, *_SEPARATORS})
        or (right and after not in {"", *CLOSERS, *_SEPARATORS})
    ):
        return f"({filled})", True
    return filled, False
