# isar-tools

[![CI Status][ci-badge]][ci]
[![PyPI][pypi-badge]][pypi]
[![conda-forge][conda-badge]][conda]
[![License][license-badge]][license]

[ci-badge]: https://img.shields.io/github/actions/workflow/status/ManuelLerchner/isar-tools/ci.yml?branch=main&style=flat-square&label=CI
[ci]: https://github.com/ManuelLerchner/isar-tools/actions/workflows/ci.yml
[pypi-badge]: https://img.shields.io/pypi/v/isar-tools?style=flat-square
[pypi]: https://pypi.org/project/isar-tools/
[conda-badge]: https://img.shields.io/conda/vn/conda-forge/isar-tools?style=flat-square
[conda]: https://anaconda.org/conda-forge/isar-tools
[license-badge]: https://img.shields.io/github/license/ManuelLerchner/isar-tools?style=flat-square
[license]: https://github.com/ManuelLerchner/isar-tools/blob/main/LICENSE

Source tooling for Isabelle/Isar projects: a formatter, project and source
checks, and statistics. Pure Python. Works on `.thy` and `ROOT` files without
running Isabelle.

![Terminal recording: isar stats prints session and theory tables for a small
demo project, isar check reports an unfinished proof (sorry), isar fmt --diff
indents a proof and removes trailing whitespace and extra blank lines, and isar
project graph prints the theory import graph.](https://raw.githubusercontent.com/ManuelLerchner/isar-tools/main/docs/demo/demo.gif)

Status: pre-alpha. See [`CHANGELOG.md`](https://github.com/ManuelLerchner/isar-tools/blob/main/CHANGELOG.md) and
[`docs/PLAN.md`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/PLAN.md).

## Install

```sh
pixi global install isar-tools  # or: conda install -c conda-forge isar-tools
pip install isar-tools          # or: uv tool install isar-tools, pipx install isar-tools
isar --help
```

Python 3.11 or newer; no runtime dependencies. In a pixi project:
`pixi add isar-tools`.

## Commands

| Command                                  | What it does                                                                               |
| ---------------------------------------- | ------------------------------------------------------------------------------------------ |
| `isar fmt [PATH...]`                     | Format theories: indentation, trailing whitespace, blank lines, and optional line wrapping |
| `isar check [GROUP] [PATH...]`           | Report problems in ROOT files, proofs, syntax, symbols, docs, and locales                  |
| `isar stats [VIEW] [PATH...]`            | Size, proof, and command statistics                                                        |
| `isar stats build BUILD_LOG`             | Where theory elaboration time went in an `isabelle build -v` log                           |
| `isar project sessions\|theories\|graph` | Sessions, theories, and the session or theory import graph                                 |
| `isar project hierarchy`                 | Class and locale declarations: parents, parameters, assumptions                            |
| `isar project names`                     | Named declarations: qualified name, kind, location, docstring; a Markdown index            |
| `isar project extract NAME...`           | The source of a declaration by name; keeps quoted declarations in sync with a manifest     |
| `isar symbols normalize PATH...`         | Rewrite symbols as `\<name>`, or as Unicode                                                |

A path is a project directory, read like `isabelle build -D` (its `ROOT`, and
`ROOTS` recursively), or a `.thy` file. Commands that read a project default to the current
directory.

Exit status: `0` success, `1` findings or differences, `2` invalid invocation or
unreadable input. Data goes to stdout, diagnostics to stderr. JSON and CSV output
use stable snake_case keys and are never coloured.

### Formatting

```sh
isar fmt                          # format every .thy below the current directory
isar fmt --check                  # list files that would change; exit 1 if any
isar fmt --diff Foo.thy           # show the change without writing
isar fmt --max-line-length 100    # also wrap long lines
isar fmt -                        # stdin to stdout, for editors
```

The formatter only changes layout. It never changes a token, never touches the
space between two tokens on a line, and never rewrites strings, cartouches,
comments, or ML. By default it only indents lines that are too shallow for their
proof structure; `--normalize` sets indentation exactly. See
[`docs/FORMATTER.md`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/FORMATTER.md).

As a git hook with [lefthook](https://github.com/evilmartians/lefthook):

```yaml
pre-commit:
  jobs:
    - name: isar-fmt
      glob: "*.thy"
      run: isar fmt {staged_files}
      stage_fixed: true
```

### Checks

```sh
isar check                        # groups project, proofs, and syntax
isar check symbols src/           # non-ASCII characters outside comments
isar check docs src/              # theories, headings, locales, classes without a text block
isar check leftovers hygiene src/ # sledgehammer, thm, nitpick without expect; tabs, CRs
isar check locales -d ~/afp/thys  # free variables in locale headers
isar check --ignore oops --format json
```

| Group       | Codes                                                                                                                                           |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `project`   | `root-syntax`, `duplicate-session`, `missing-theory`, `missing-directory`, `missing-document-file`, `duplicate-theory-name`, `unreached-theory` |
| `proofs`    | `unfinished-proof` (`sorry`, `\<proof>`), `oops`, `unclosed-proof`                                                                              |
| `syntax`    | `lexical-error`, `document-argument`, `theory-name`, `invalid-utf8`                                                                             |
| `symbols`   | `non-ascii` (opt-in)                                                                                                                            |
| `docs`      | `undocumented-theory`, `undocumented-heading`, `undocumented-locale`, `undocumented-class` (opt-in)                                             |
| `locales`   | `locale-free-variable` (opt-in, heuristic)                                                                                                      |
| `hygiene`   | `tab`, `carriage-return`, `bidi-control`, `reserved-file-name` (opt-in)                                                                         |
| `leftovers` | `proof-search`, `counterexample-search`, `diagnostic-command` (opt-in)                                                                          |

Project checks run for directory arguments only. `isar check --help` describes
every code.

`locales` is heuristic. Inside the terms of a `locale` or `context` header,
Isabelle reads an unknown identifier as a free variable and generalizes over
it, so an assumption citing a deleted or misspelt constant still builds. The
check reports identifiers that are no parameter of the header (its `fixes`,
`for` clause, `defines`, or those of the locales it extends, resolved through
imports), not bound in the term, and not used anywhere else in the project or
in the `-d` theories it imports. Only names of at least four characters with an
underscore (or `\<^sub>`) are reported; `--allow NAME` (repeatable) accepts a
name. Inner syntax is approximated lexically: see `isar_tools/checks/locales.py`.

### Commands of other sessions

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

### Names

```sh
isar project names --kind locale                  # every locale, as Theory.locale
isar project names --format markdown > NAMES.md   # an index with docstrings
isar project names --name Foo.loc.bar_lemma       # exit 1 if no such declaration
isar project names --derived                      # also f_def, f.simps, L.intro, q.fact
isar project names "$ISABELLE_HOME/src/HOL/Orderings.thy"   # one theory file alone
```

Names are qualified as Isabelle renders them: a lemma inside `context loc` is
`Theory.loc.name`, and a datatype's constructors and selectors and a record's
fields are named in their type (`Theory.t.C`). With `--name`, a qualifier
naming the wrong scope does not match, and the error suggests the names that
exist, so links into rendered theories can be checked without building them. The docstring is a `text` block
directly before the declaration.

### Quoting declarations

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

### Statistics

```sh
isar stats                               # sessions, then the largest theories
isar stats proofs --top 10               # the longest proofs
isar stats style --max-line-length 100   # long theories, long lines, sorry, watched methods
isar stats commands --by theory --format json   # command counts per theory
isar stats build build.log --budget HOL-Library=0
isar stats build build.log --budget TD=8 --default-budget 0 --project .  # every other library: 0
```

### Configuration

Options a project always wants go in `[tool.isar]` in `pyproject.toml`, or in an
`isar.toml` (same keys, at the top level). The file is found by searching upward
from the working directory.

```toml
[tool.isar]
include = ["$AFP", "vendor/td-verification"]  # like -d; skipped with a note if absent
exclude = ["src/**/generated/**"]             # like --exclude

[tool.isar.fmt]
max-line-length = 100    # also: indent, max-blank-lines, normalize

[tool.isar.check]
groups = ["project", "proofs", "syntax"]      # also: ignore, allow

[tool.isar.stats]
max-line-length = 100    # also: watch
```

Paths and globs are relative to the file. Command-line options win; `-d` and
`--exclude` add to the lists, and `--max-line-length 0` turns configured wrapping off.
A glob excludes matching files and everything below matching directories, also when a
file is named on the command line (as a git hook does).

## Limits

- Nothing runs Isabelle, so nothing is type-checked or proved. A formatted file
  is guaranteed to contain the same tokens; building it is the project's CI's
  job.
- The built-in command table is hand-written, and the AFP table is generated
  from one AFP revision (`scripts/gen_afp_commands.py`). A command of a session
  that is in neither and not passed with `-d` is read as part of the previous
  command.
- `project names --derived` adds the usual derived facts (`f_def`, `f.simps`,
  `P.intros`, `t.inject`, `L.intro`, ...) and the facts of qualified
  theory-level interpretations (`q.fact`), from the interpreted locale's own
  facts only; facts a locale inherits, and names made by other packages, are
  not listed.
- `project hierarchy` follows declared parents, not `sublocale`, `subclass`, or
  `interpretation`.
- `stats build` reads one log line format, observed in Isabelle2025 logs.

## Development

Requires [pixi](https://pixi.sh).

```sh
pixi run pre-commit-install  # git hooks
pixi run test
pixi run coverage            # 100% line and branch coverage required
pixi run typecheck           # pyright, strict
pixi run lint
pixi run isar --help
pixi run demo                # re-record docs/demo/demo.gif with VHS
pixi run demo-check          # run the demo commands without recording
ISAR_CORPUS=~/afp/thys pixi run corpus   # integration tests over real projects
```

Expected output lives in golden files under `tests/golden/` and
`tests/formatter/`. `UPDATE_GOLDEN=1 pixi run test` rewrites them, so a change in
output shows up as a diff in review.

The demo GIF is generated by [VHS](https://github.com/charmbracelet/vhs) from
[`docs/demo/demo.tape`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/demo/demo.tape), which runs the real commands on the
small project in [`docs/demo/project`](https://github.com/ManuelLerchner/isar-tools/tree/main/docs/demo/project). The `demo` task uses
its own pixi environment, so VHS, ttyd, and ffmpeg stay out of the default one.

### Releasing

1. Check that formatting cannot break a build: format a real project with the
   release candidate and build it with Isabelle (for Voblint, its
   `isar fmt round trip` workflow or the same steps locally).
2. In `CHANGELOG.md`, rename `## Unreleased` to `## X.Y.Z (YYYY-MM-DD)` and merge.
3. Tag the merge commit and push the tag (`git tag -a vX.Y.Z -m "isar-tools X.Y.Z"`,
   `git push origin vX.Y.Z`). The `Build` workflow takes the version from the tag
   and publishes to PyPI; the conda-forge feedstock's bot opens the update.

## License

MIT
