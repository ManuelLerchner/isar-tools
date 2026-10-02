# Project views

The `isar project` commands read a project's sources and report its structure. `isar --help` and `isar project COMMAND --help` list every option.

## Commands of other sessions

Whether a word is an Isar command depends on the theories a file imports. The
built-in table covers Pure and HOL, commands declared in the theory headers of
the project are found automatically, and a generated table covers the commands
of AFP entries (such as `derive` from `Deriving`), so no AFP checkout is needed.
For commands of other projects, or of an AFP newer than the table, pass their
directory with `-d`, as with `isabelle build -d`:

```sh
isar check -d ~/afp/thys .
isar project hierarchy --root numeric_domain -d ~/afp/thys --format json
```

## Session layers

```sh
isar project graph --layers                  # layer, session, and what it rests on
isar project graph --layers --format dot     # one rank per layer
```

A session rests on its parent, its `sessions` entries, and the sessions whose
theories its theories import. Its layer is one above the highest of those
(1 if it rests on no known session), so a drawing of the development as strata
follows the ROOT files and imports. Sessions of `-d` directories that the
project rests on are included; JSON adds `layers` and the `imports` edges.

## Names

```sh
isar project names --kind locale                  # every locale, as Theory.locale
isar project names --format markdown > NAMES.md   # an index with docstrings
isar project names --name Foo.loc.bar_lemma       # exit 1 if no such declaration
isar project names --derived                      # also f_def, f.simps, L.intro, q.fact
isar project names "$ISABELLE_HOME/src/HOL/Orderings.thy"   # one theory file alone
isar project names --kind fact --statements --format json   # each lemma's statement
```

Names are qualified as Isabelle renders them: a lemma inside `context loc` is
`Theory.loc.name`, and a datatype's constructors and selectors and a record's
fields are named in their type (`Theory.t.C`). With `--name`, a qualifier
naming the wrong scope does not match, and the error suggests the names that
exist, so links into rendered theories can be checked without building them.
JSON and CSV rows carry a constant's `mixfix`, its `notation` (the first string
of the mixfix), and the syntax `mode` of `abbreviation (input)`, for constants,
record fields, constructors, and locale parameters, `for` clause included. The docstring is a `text` block
directly before the declaration.

## Quoting declarations

```sh
isar project extract combine_env locale_name.lemma_name
isar project extract --statement lemma_name     # without the proof
isar project extract "sign :: numeric_domain" sign_tf   # an instance, an interpretation
isar project extract --manifest snippets.toml --out generated/ --write   # regenerate
isar project extract --manifest snippets.toml --out generated/ --check   # diff; exit 1 on drift
```

A name is `name`, `locale.name`, `Theory.name`, or `Theory.locale.name`, a
class instance `type :: class`, or the qualifier of an interpretation
(`q` for `interpretation q: loc`), and must identify one declaration. The
project's declarations come first, then those of `-d` directories; a
declaration hides the parameters, fields, and constructors that others have of
the same name; its source is the command and, for a goal, its
proof. With `--statement` it is the statement alone: no proof, and no `begin` of
a locale, class, or instantiation. A manifest lists snippets as TOML tables,
each written to `KEY.thy`, so a document that quotes a definition fails its
check when the definition changes or is renamed:

```toml
[snippets.combine_env]
why = "shown in chapter 3"     # free text, ignored
[snippets.succ_pos]
file = "src/B.thy"             # choose between declarations of the same name
proof = true                   # keep the proof, also with --statement
[snippets.succ_pos_short]
name = "B.succ_pos"            # what to extract, if not the key
[snippets.order]
file = "~~/src/HOL/Orderings.thy"   # Isabelle's own theories, below $ISABELLE_HOME
```

A `~~/` file is read below the `ISABELLE_HOME` environment variable and printed
back as `(* ~~/src/HOL/Orderings.thy *)`; without the variable, such entries are
skipped with a note.

## Notation

```sh
isar project notation notation.toml                                  # JSON to stdout
isar project notation notation.toml --out gen/notation.json --write
isar project notation notation.toml --out gen/notation.json --check  # diff; exit 1 on drift
isar project notation notation.toml --browser-info browser_info      # every anchor must exist
```

A document that explains a formalization shows its symbols, and a hand-typed
table of them drifts from the theories. The manifest names the declarations and
the argument names to show; the rest is read off each declaration:

```toml
[notation.widen]
args = ["a", "b"]                   # filled into the mixfix's _ slots, the rest applied after
reads = "a widened by b"            # anything else is ignored: keep your prose here
[notation.step]
name = "walk.step"                  # a NAME as extract takes it; default: the key
args = ["x", "y"]
[notation."walk.reach"]
file = "src/Walk.thy"               # choose between declarations of the same name
```

For `fixes widen :: ... (infixl "\<nabla>" 65)` in a class, the entry is

```json
{
  "key": "widen",
  "name": "Lattice.widening_class.widen",
  "kind": "class_parameter",
  "command": "fixes",
  "scope": "global",
  "owner": "widening",
  "symbol": "a \\<nabla> b",
  "unicode": "a ∇ b",
  "printed": true,
  ...
}
```

with also `theory`, `session`, `path`, `line`, `mixfix` (as written),
`notation` (its template, `_ \<nabla> _` for an infix), `args`, `mode`
(`input` or `output` of an abbreviation), `expansion` (an abbreviation's `lhs`
and `rhs`), and the HTML anchors `anchor`, `url`, `owner_anchor`, and
`owner_url`, as `project names` gives them. `kind` is the shape:

| `kind`                | Declaration                                                                     | `scope`    |
| --------------------- | ------------------------------------------------------------------------------- | ---------- |
| `constant`            | `consts`, `definition`, `abbreviation`, `fun`, `inductive`, ... at theory level | `global`   |
| `class_parameter`     | `fixes` of a class                                                              | `global`   |
| `record_field`        | a field of a record                                                             | `global`   |
| `locale_parameter`    | `fixes` or `for` of a locale; it has no anchor of its own, its locale has       | the locale |
| `locale_abbreviation` | `abbreviation` inside a locale or class, also via `context`                     | the locale |

Isabelle never prints an `abbreviation (input)` back, so its `printed` is
false. Any other declaration, such as a constant defined inside a locale (whose
notation outside it takes the locale's parameters), a datatype constructor, or
a `binder` or `structure` mixfix, fails with its location; so does a mixfix
with more `_` slots than `args`, and an abbreviation that is not one
`lhs \<equiv> rhs` equation. Notation added later with the `notation` command
is not read. Nothing is written while any entry fails.

With `--browser-info`, an anchor the sources cannot give is looked up in the
build, as `project anchors` does: that of a theory no session owns, and that of
an owner the project does not declare (`context order begin` gives HOL's
`order`). `--prefer` chooses between rival definitions there.

## Anchors in a build

```sh
isar project anchors --browser-info browser_info --format json      # every anchor
isar project anchors --browser-info browser_info lfp "order|locale" # by name
isar project anchors --browser-info browser_info --kind fact --kind thm sound \
  --prefer MyChapter/ --prefer HOL/HOL/
```

`project names` gives the anchors of the project from its sources. A build
also holds those of HOL and of every library session it rendered. A NAME is any
dotted suffix of an anchor (`loc.name`, `name`), or `Theory.name` for a member
of a locale or type when no suffix matches, with `|kind` or `--kind` (tried in
order) to choose the kind. The ids of one definition count once: a lemma's
`fact` and `thm`, a class's `locale` and `class`, and `T.c.x` and
`T.c_class.x`. A copy of another session's theory (`Owner.Theory.html`) is
skipped. A name that matches several definitions, such as a constant two
locales declare or a fact an interpretation copies, is an error that lists
them; `--prefer PREFIX` (repeatable, first is best) keeps the definitions on
pages below the first prefix that has any.
