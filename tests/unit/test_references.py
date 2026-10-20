from pathlib import Path

from isar_tools.project.model import Project
from isar_tools.project.names import Entity
from isar_tools.project.references import References, walk
from tests.conftest import MakeProject

# B is read before A, which it imports.
ROOT = "session S = HOL + theories B A C\n"
A = r"""theory A imports Main begin
text \<open>@{thm f_def} is cited by no declaration.\<close>
definition f :: nat where "f = 0"
fun g :: "nat \<Rightarrow> nat" where "g n = n"
lemma f_zero: "f = 0" by (simp add: f_def)
locale L = fixes x :: nat assumes x_pos: "x > 0"
begin
lemma in_L: "x > 0" by (rule x_pos)
end
locale M = L + assumes x_big: "x > 1"
begin
lemma in_M: "x > 0" using x_pos in_L by simp
end
locale N = fixes y :: nat
lemma (in N) in_N: "y = y" using x_pos by simp
lemma outside: "True" using L.in_L f_zero g.simps by simp
class c = fixes op :: 'a assumes op_ax: "op = op"
lemma (in c) in_c: "op = op" by (rule op_ax)
locale loop = loop2
locale loop2 = loop
lemma (in loop) in_loop: "True" using x_pos by simp
fun ev :: "nat \<Rightarrow> bool" and od :: "nat \<Rightarrow> bool" where
  "ev 0 = (f = 0)" | "ev (Suc n) = od n" | "od 0 = False" | "od (Suc n) = ev n"
lemma evens: "ev 0" using outside ev.simps by simp
end
"""
B = r"""theory B imports A begin
lemma uses_a: "True" using f_zero f_def by simp
end
"""
C = r"""theory C imports Main begin
lemma no_import: "True" using f_zero by simp
end
"""


def references(make_project: MakeProject) -> References:
    base = make_project({"ROOT": ROOT, "A.thy": A, "B.thy": B, "C.thy": C})
    return References(Project.load(base))


def names(entities: set[Entity] | None) -> list[str]:
    return sorted(e.qualified for e in entities or ())


def by_name(refs: References, qualified: str) -> Entity:
    every = {e for edges in (refs.cites, refs.cited_by) for es in edges.values() for e in es}
    return next(e for e in every | set(refs.cites) if e.qualified == qualified)


def test_cites(make_project: MakeProject) -> None:
    refs = references(make_project)
    cites = {e.qualified: names(es) for e, es in refs.cites.items()}
    assert cites == {
        "A.L.in_L": ["A.L.x", "A.L.x_pos"],
        "A.M": ["A.L", "A.L.x"],
        "A.M.in_M": ["A.L.in_L", "A.L.x", "A.L.x_pos"],
        "A.N.in_N": ["A.N", "A.N.y"],
        "A.c.in_c": ["A.c", "A.c_class.op", "A.c_class.op_ax"],
        "A.ev": ["A.f"],
        "A.evens": ["A.ev", "A.outside"],
        "A.f_zero": ["A.f"],
        "A.loop.in_loop": ["A.loop"],
        "A.loop2": ["A.loop"],
        "A.od": ["A.f"],
        "A.outside": ["A.L.in_L", "A.f_zero", "A.g"],
        "B.uses_a": ["A.f", "A.f_zero"],
    }
    assert names(refs.cited_by[by_name(refs, "A.f")]) == ["A.ev", "A.f_zero", "A.od", "B.uses_a"]
    assert refs.ancestors("loop") == {"loop", "loop2"}


def test_walk(make_project: MakeProject) -> None:
    refs = references(make_project)
    f = by_name(refs, "A.f")
    direct = [(e.qualified, d) for e, d in walk(refs.cited_by, f, transitive=False)]
    assert direct == [("A.f_zero", 1), ("A.ev", 1), ("A.od", 1), ("B.uses_a", 1)]
    every = [(e.qualified, d) for e, d in walk(refs.cited_by, f, transitive=True)]
    assert every == [
        ("A.f_zero", 1),
        ("A.ev", 1),
        ("A.od", 1),
        ("B.uses_a", 1),
        ("A.outside", 2),
        ("A.evens", 2),
    ]
    assert walk(refs.cites, f, transitive=True) == []


def test_unreadable_bytes(make_project: MakeProject) -> None:
    base = make_project({"ROOT": "session S = HOL + theories T\n"})
    (base / "T.thy").write_bytes(b'theory T imports Main begin\nlemma \xb5: "True" by simp\nend\n')
    assert References(Project.load(base)).cites == {}


def test_reach(make_project: MakeProject) -> None:
    refs = references(make_project)
    assert sorted(p.name for p in refs.reach(Path(make_project({}) / "B.thy"))) == [
        "A.thy",
        "B.thy",
    ]
