from pathlib import Path

import pytest

from isar_tools.checks.attributes import check_attributes
from isar_tools.checks.findings import Finding
from isar_tools.source.theory import parse_theory


def findings(body: str) -> list[Finding]:
    return check_attributes(Path("T.thy"), parse_theory(body))


def fixed(body: str) -> str:
    found = findings(body)
    assert len(found) == 1
    fix = found[0].fix
    assert fix is not None
    assert not fix.safe
    for edit in sorted(fix.edits, key=lambda e: e.start, reverse=True):
        body = body[: edit.start] + edit.text + body[edit.end :]
    assert not findings(body)
    return body


@pytest.mark.parametrize(
    "attribute", ["code_unfold", "simp", "intro", "dest!", "elim?", "iff add", "code", "code_post"]
)
def test_definition(attribute: str) -> None:
    source = 'definition foo :: nat where\n  "foo = 0"\n'
    assert fixed(source + f"declare foo_def [{attribute}]\n") == source.replace(
        "where", f"where [{attribute}]:"
    )


@pytest.mark.parametrize(
    ("source", "fact", "expected"),
    [
        ('definition foo where eq: "foo = 0"', "eq", 'definition foo where eq [simp]: "foo = 0"'),
        (
            'definition foo where [code_unfold]: "foo = 0"',
            "foo_def",
            'definition foo where [code_unfold, simp]: "foo = 0"',
        ),
        (
            'definition foo where eq [code_unfold]: "foo = 0"',
            "eq",
            'definition foo where eq [code_unfold, simp]: "foo = 0"',
        ),
        (
            'definition "foo" where "eq": "foo = 0"',
            "eq",
            'definition "foo" where "eq" [simp]: "foo = 0"',
        ),
        ('definition foo where []: "foo = 0"', "foo_def", 'definition foo where [simp]: "foo = 0"'),
    ],
)
def test_equation_binding(source: str, fact: str, expected: str) -> None:
    assert fixed(f"{source}\ndeclare {fact} [simp]\n") == expected + "\n"


@pytest.mark.parametrize(
    "proof", ["by simp", "apply simp\ndone", "proof -\n  show True by simp\nqed"]
)
@pytest.mark.parametrize("command", ["lemma", "theorem", "corollary", "proposition"])
def test_theorem(command: str, proof: str) -> None:
    source = f'{command} foo: "True"\n{proof}\n'
    assert fixed(source + "declare foo [intro!, simp]\n") == source.replace(
        "foo:", "foo [intro!, simp]:"
    )


def test_existing_theorem_attributes() -> None:
    assert fixed('lemma foo [simp]: "True" by simp\ndeclare foo [intro]\n') == (
        'lemma foo [simp, intro]: "True" by simp\n'
    )


@pytest.mark.parametrize("command", ["inductive", "inductive_set", "coinductive"])
def test_inductive_rules(command: str) -> None:
    source = (
        f'{command} p :: "nat => bool" for x and y where\n'
        '  zero: "p 0"\n| step [simp]: "p n ==> p (Suc n)"\n'
    )
    assert fixed(source + "declare p.intros [intro]\n") == source.replace(
        "zero:", "zero [intro]:"
    ).replace("[simp]", "[simp, intro]")


@pytest.mark.parametrize(
    "body",
    [
        "declare foo_def [simp]",
        'definition foo where "foo = 0"\ndeclare bar_def [simp]',
        'definition foo where eq [simp: "foo = 0"\ndeclare eq [simp]',
        'definition foo where [simp] "foo = 0"\ndeclare foo_def [simp]',
        "definition foo where [simp\ndeclare foo_def [simp]",
        "definition foo where [simp]:\ndeclare foo_def [simp]",
        "definition foo where eq\ndeclare foo_def [simp]",
        "definition foo\ndeclare foo_def [simp]",
        'definition foo where eq: "foo = 0"\ndeclare foo_def [simp]',
        'definition foo where "foo = 0"\nlemma t: "True" by simp\ndeclare foo_def [simp]',
        'definition foo where "foo = 0"\nend\ndeclare foo_def [simp]',
        'definition foo where "foo = 0"\ncontext begin\ndeclare foo_def [simp]',
        'definition (in L) foo where "foo = 0"\ndeclare L.foo_def [simp]',
        'definition foo where "foo = 0"\ndeclare (in L) foo_def [simp]',
        'definition foo where "foo = 0"\ndeclare foo_def(1) [simp]',
        'definition foo where "foo = 0"\ndeclare foo_def [simp] bar [intro]',
        'definition foo where "foo = 0"\ndeclare foo_def [simp del]',
        'definition foo where "foo = 0"\ndeclare foo_def [symmetric, simp]',
        'definition foo where "foo = 0"\ndeclare foo_def [of x, simp]',
        'definition foo where "foo = 0"\ndeclare foo_def []',
        'definition foo where "foo = 0"\ndeclare foo_def [simp',
        'definition foo where "foo = 0"\ntext ‹policy›\ndeclare foo_def [simp]',
        'lemma foo: "True" oops\ndeclare foo [simp]',
        'lemma foo: "True" sorry\ndeclare foo [simp]',
        'lemma foo: "True"\ndeclare foo [simp]',
        'lemma foo: "True" and bar: "True" by simp_all\ndeclare foo [simp]',
        'inductive p and q where r: "p"\ndeclare p.intros [intro]',
        'inductive p where "p"\ndeclare p.intros [intro]',
        'inductive p where r: "p"\ndeclare q.intros [intro]',
        "inductive p where\ndeclare p.intros [intro]",
        "inductive p where r:\ndeclare p.intros [intro]",
        "inductive p where r: invalid\ndeclare p.intros [intro]",
        'inductive p where r: "p" for x\ndeclare p.intros [intro]',
        'fun foo where "foo x = x"\ndeclare foo.simps [simp]',
        'lemma "True" proof -\n have foo: "True" by simp\n'
        " declare foo [intro]\n show True by simp\nqed",
    ],
)
def test_exclusions(body: str) -> None:
    assert not findings(body)


@pytest.mark.parametrize(
    "attrs", ["custom_rules", "custom_rule [a, b]", "intro 2", "simp, custom_rules"]
)
def test_unknown_attributes_report_only(attrs: str) -> None:
    found = findings(f'definition foo where "foo = 0"\ndeclare foo_def [{attrs}]')
    assert len(found) == 1
    assert found[0].fix is None


def test_comments_preserved() -> None:
    assert fixed(
        'definition foo where "foo = 0"\n(* reason *)\ndeclare foo_def [simp] (* policy *)\n'
    ) == ('definition foo where [simp]: "foo = 0"\n(* reason *)\n (* policy *)\n')
    found = findings('definition foo where "foo = 0"\ndeclare foo_def [(* policy *) simp]')
    assert len(found) == 1
    assert found[0].fix is None


def test_layout() -> None:
    assert fixed('definition foo where "foo = 0"\r\n  declare\r\n    foo_def [simp]\r\nend') == (
        'definition foo where [simp]: "foo = 0"\r\nend'
    )
    assert fixed('definition foo where "foo = 0" declare foo_def [simp] end') == (
        'definition foo where [simp]: "foo = 0"  end'
    )
