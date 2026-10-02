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

Linting, formatting, and project analysis for Isabelle/Isar. Pure Python: it
reads `.thy` and `ROOT` files the way `isabelle build` finds them, without
running Isabelle, and answers in seconds.

![Terminal recording: isar stats prints session and theory tables for a small
demo project, isar check reports an unfinished proof (sorry), isar fmt --diff
indents a proof and removes trailing whitespace and extra blank lines, and isar
project graph prints the theory import graph.](https://raw.githubusercontent.com/ManuelLerchner/isar-tools/main/docs/demo/demo.gif)

## Why

Isabelle checks that every proof goes through. It has nothing to say about a
lemma no proof cites, an import another import already brings in, a constant
written out next to the notation the project gave it, a locale assumption no
proof uses, or a `sorry` left in a theory nobody builds. In a development of a
few hundred theories these pile up, the build slows down, and reviewers check
style by eye. Other languages have formatters, linters, and dead-code finders
for this. Large Isabelle projects mostly have conventions in a README.

isar-tools is that missing tooling: a formatter that only touches layout, about
fifty checks, statistics, and views of a project's sessions, theories, and
declarations. It fits a pre-commit hook or a CI job next to the build.

Status: alpha. Published on PyPI and conda-forge and used by a real project;
minor versions may still add commands and JSON columns. See [`CHANGELOG.md`](https://github.com/ManuelLerchner/isar-tools/blob/main/CHANGELOG.md) and
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

| Command                                   | What it does                                                                               |
| ----------------------------------------- | ------------------------------------------------------------------------------------------ |
| `isar fmt [PATH...]`                      | Format theories: indentation, trailing whitespace, blank lines, and optional line wrapping |
| `isar check [GROUP] [PATH...]`            | Lint ROOT files and theories: proofs, notation, unused and redundant lemmas, and more      |
| `isar stats [VIEW] [PATH...]`             | Size, proof, and command statistics                                                        |
| `isar stats build BUILD_LOG`              | Where theory elaboration time went in an `isabelle build -v` log                           |
| `isar project sessions\|theories\|graph`  | Sessions, theories, and the session or theory import graph; session layers                 |
| `isar project hierarchy`                  | Class and locale declarations: parents, parameters, assumptions                            |
| `isar project instances`                  | Class instances and locale interpretations, with their class or locale                     |
| `isar project names`                      | Named declarations: qualified name, kind, location, docstring; a Markdown index            |
| `isar project extract NAME...`            | The source of a declaration by name; keeps quoted declarations in sync with a manifest     |
| `isar project notation TOML`              | The symbols declarations introduce, from their mixfix; keeps a notation table in sync      |
| `isar project anchors --browser-info DIR` | Anchors of a built HTML presentation, HOL included, by name                                |
| `isar symbols normalize PATH...`          | Rewrite symbols as `\<name>`, or as Unicode                                                |

A path is a project directory, read like `isabelle build -D` (its `ROOT`, and
`ROOTS` recursively), or a `.thy` file. Commands that read a project default to the current
directory.

Exit status: `0` success, `1` findings or differences, `2` invalid invocation or
unreadable input. Data goes to stdout, diagnostics to stderr. JSON and CSV output
use stable snake_case keys and are never coloured.

## Checks

```sh
isar check                           # groups project, proofs, and syntax
isar check notation unused src/      # name more groups to run them
isar check --ignore oops --format json
isar check all --fix                 # every group; apply the fixes that keep meaning
isar check all --fix=all             # also the ones only a build can confirm
```

A finding marked `[*]` carries a fix. `--fix` (safe) rewrites `(simp add:)`,
duplicate facts, redundant imports, tabs, CR line endings, bidi controls, and
non-ASCII symbols outside ML. `--fix=all` also drops unused imports and rewrites
terms into their notation or abbreviation; build after it. Unused and redundant
lemmas are only reported: whether one is dead is a decision, not a rewrite.

A tour, from [`docs/showcase/Tour.thy`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/showcase/Tour.thy):

<!-- tour:begin -->

```isabelle
theory Tour
  imports Base
begin

text \<open>A few findings of \<^verbatim>\<open>isar check\<close>.\<close>

lemma join_comm: "a \<squnion>\<^sub>m b = b \<squnion>\<^sub>m a"
  by (simp add: join_def)

lemma join_comm_again: "x \<squnion>\<^sub>m y = y \<squnion>\<^sub>m x"
  by (simp add:)

lemma join_idem: "join a a = a"
  apply (simp add: join_def)
  done

lemma join_bound: "a \<le> a \<squnion>\<^sub>m b"
  sorry

end
```

```console
$ isar check proofs notation methods redundant Tour.thy
Tour.thy:10:7: duplicate-lemma: join_comm_again states join_comm (Tour.thy:7) again
Tour.thy:11:12: empty-modifier: add: lists nothing
Tour.thy:13:19: spelled-out-notation: join is written out; its notation is _ \<squnion>\<^sub>m _
Tour.thy:14:3: single-apply: one apply and done: write by
Tour.thy:18:3: unfinished-proof: sorry leaves the goal unproved
```

<!-- tour:end -->

<!-- groups:begin -->

| Group                                                                                          | Codes                                                                                                                                                          | Runs       |
| ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| [`project`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#project)     | `root-syntax`, `duplicate-session`, `missing-theory`, `missing-directory`, `theory-path`, `missing-document-file`, `duplicate-theory-name`, `unreached-theory` | by default |
| [`proofs`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#proofs)       | `unfinished-proof`, `oops`, `unclosed-proof`                                                                                                                   | by default |
| [`syntax`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#syntax)       | `lexical-error`, `document-argument`, `theory-name`, `invalid-utf8`                                                                                            | by default |
| [`symbols`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#symbols)     | `non-ascii`                                                                                                                                                    | when named |
| [`docs`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#docs)           | `undocumented-theory`, `undocumented-heading`, `undocumented-locale`, `undocumented-class`                                                                     | when named |
| [`locales`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#locales)     | `locale-free-variable`                                                                                                                                         | when named |
| [`notation`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#notation)   | `spelled-out-notation`, `spelled-out-abbreviation`                                                                                                             | when named |
| [`unused`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#unused)       | `unused-lemma`, `redundant-import`, `unused-import`, `unused-assumption`                                                                                       | when named |
| [`redundant`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#redundant) | `duplicate-lemma`, `subsumed-lemma`                                                                                                                            | when named |
| [`hygiene`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#hygiene)     | `tab`, `carriage-return`, `bidi-control`, `reserved-file-name`                                                                                                 | when named |
| [`leftovers`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#leftovers) | `proof-search`, `counterexample-search`, `goal-reordering`, `backtracking`, `diagnostic-command`                                                               | when named |
| [`methods`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#methods)     | `empty-modifier`, `duplicate-fact`, `single-apply`                                                                                                             | when named |
| [`retired`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#retired)     | `retired-identifier`                                                                                                                                           | when named |
| [`prose`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#prose)         | `prose-reference`, `prose-underscore`                                                                                                                          | when named |
| [`links`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md#links)         | `broken-link`, `broken-anchor`, `anchor-name`                                                                                                                  | when named |

<!-- groups:end -->

[`docs/CHECKS.md`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/CHECKS.md) explains every group and shows an example
of every code, generated from the [showcase project](https://github.com/ManuelLerchner/isar-tools/tree/main/docs/showcase). A comment
`(* isar-ignore: CODE *)` silences a finding on its line, or on the next line
when it stands alone.

## Formatting

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

## Project views

```sh
isar project graph --layers          # sessions as strata
isar project names --format markdown > NAMES.md
isar project extract --manifest snippets.toml --out generated/ --check
isar project notation notation.toml --out gen/notation.json --check
```

[`docs/PROJECT.md`](https://github.com/ManuelLerchner/isar-tools/blob/main/docs/PROJECT.md) describes session layers, names, quoting
declarations, notation tables, anchors of a build, and commands of other
sessions (`-d`).

## Statistics

```sh
isar stats                               # sessions, then the largest theories
isar stats proofs --top 10               # the longest proofs
isar stats style --max-line-length 100   # long theories, long lines, sorry, watched methods
isar stats commands --by theory --format json   # command counts per theory
isar stats build build.log --budget HOL-Library=0
isar stats build build.log --budget TD=8 --default-budget 0 --project .  # every other library: 0
```

## Configuration

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
groups = ["project", "proofs", "syntax"]      # also: ignore, allow, leaf-sessions
retired-file = "retired_identifiers.txt"      # also: retired = ["name", ...]

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
pixi run typecheck           # pyright (strict), then ty
pixi run lint
pixi run isar --help
pixi run demo                # re-record docs/demo/demo.gif with VHS
pixi run demo-check          # run the demo commands without recording
pixi run checks-doc          # regenerate docs/CHECKS.md and the README's check sections
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
