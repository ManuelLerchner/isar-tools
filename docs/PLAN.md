# isar-tools: capability and implementation plan

## 1. Purpose

`isar-tools` is a standalone source-tooling suite for Isabelle/Isar projects:

```text
isar fmt       Format Isabelle/Isar source files
isar check     Check project and source hygiene
isar stats     Report source, proof, and build statistics
isar project   Inspect Isabelle project structure
isar symbols   Inspect or normalize Isabelle symbols
```

The formatter is the flagship. Project validation and statistics are
first-class capabilities derived in part from prototypes in the Voblint
repository. Tools work without an Isabelle build wherever possible.

Distribution targets, in order: CLI, Python library where useful, PyPI,
conda-forge, possibly the Isabelle Tools Collection.

## 2. Scope

### Formatting

```text
isar fmt PATH...
isar fmt --check PATH...
isar fmt --diff PATH...
```

Deterministic formatting of `.thy` files. Initial responsibilities:
outer-structure indentation, whitespace and blank-line normalization,
theory/import layout, theorem statement layout (`assumes`/`and`/`shows`),
`proof`/`qed`, `case`/`next`, `using`, `unfolding`, `by`, conservative line
wrapping.

Terms, propositions, ML bodies, and document text are treated as opaque. The
formatter must not change proof semantics.

### Project validation

```text
isar check PATH
isar check project PATH
isar check proofs PATH
isar check symbols PATH
isar check document PATH
```

- Project/session: every `ROOT` directory entry exists; every theory entry
  resolves; invalid slash-containing theory entries; duplicate theory names on
  one search path; theories owned by a session but never reached by it;
  malformed structure detectable without Isabelle. Adapt Voblint's
  `check_root_entries.py`; prefer `isabelle-layout` for parsing.
- Proof source: `sorry`, `oops`, unfinished proofs detectable reliably from
  source. Do not duplicate `isabelle-linter`.
- Symbols: configurable encoding policy (`isar check symbols`,
  `isar symbols normalize`). One shared symbol table, replacing Voblint's
  separate checker and normalizer tables.
- Document: unsafe raw document text, lexically malformed cartouches.
  Heuristic prose-reference checks stay experimental until validated on
  external projects.

### Statistics

```text
isar stats PATH
isar stats sessions|theories|proofs|style PATH
isar stats build BUILD_LOG
```

Port and generalize Voblint's `thy_stats.py`: theory count; source, code,
prose, blank lines; declarations by kind; theorem/proof counts; proof and
statement lengths; largest theories and proofs; symbol-aware line length;
selected proof-method usage; `sorry`/`oops` counts; per-session aggregation.

Output formats `text`, `markdown`, `json`, `csv`. Machine-readable output is a
stable interface and is tested.

Build statistics generalize Voblint's `check_build_reelaboration.py`: sessions
built, theories elaborated, inherited theories where available, unexpected
re-elaboration, per-session totals, optional baseline comparison. Unknown
build-log formats fail explicitly.

### Project inspection

```text
isar project sessions PATH
isar project theories PATH
isar project graph PATH --format text|json|dot
```

Do not reimplement what `isabelle-query` already provides well unless a
smaller stable internal model is needed.

## 3. Non-goals (first releases)

Proof search; fact search; semantic dependency analysis; automatic proof
rewriting; `apply` to Isar conversion; theorem planning; language server;
editor extensions; build orchestration; AFP management; Voblint-specific
code-generation checks; thesis or website tooling.

Complement, do not duplicate: `isabelle-linter`, `isabelle-query`,
`isabelle-layout`, IsabelleBlueprint, editor/LSP projects.

## 4. Architecture

One common source/project representation. `fmt`, `check`, and `stats` never
parse Isabelle independently.

```text
filesystem
    -> project/session discovery
    -> source tokenization
    -> common model
         -> fmt
         -> checks
         -> stats   (+ build-log parser, source-independent)
```

## 5. Parsing strategy

No complete Isabelle AST. The formatter needs reliable regions: comments
(nested), strings, cartouches, document commands, ML bodies, outer-syntax
commands, proof-command spans, theory headers. Quoted terms stay opaque.

The decision goes in `docs/PARSER_DECISION.md`. Default if
the dependencies fall short: reuse only the project-layout layer and write the
minimum lossless lexer the formatter needs.

## 6. Formatter invariants (mandatory)

- Idempotence: `fmt(fmt(s)) == fmt(s)`, property-tested.
- Content preservation: `tokens(s) == tokens(fmt(s))` ignoring layout tokens.
- Opaque regions unchanged unless a rule owns them: comments, ML, document
  prose, quoted terms.
- Stable diffs: a local edit does not reformat unrelated code.
- Validity: corpus projects still build after formatting.
- Line endings preserved (Windows is a supported platform).

## 7. Initial formatter policy

Input:

```isabelle
lemma foo:
assumes "A"
and "B"
shows "C"
proof -
have h: "D"
using assms
by auto
show ?thesis
using h
by auto
qed
```

Output:

```isabelle
lemma foo:
  assumes "A"
    and "B"
  shows "C"
proof -
  have h: "D"
    using assms
    by auto

  show ?thesis
    using h
    by auto
qed
```

## 8. Voblint prototypes

| Priority | Script                                                   | Target                                                     |
| -------- | -------------------------------------------------------- | ---------------------------------------------------------- |
| High     | `thy_stats.py`                                           | `stats/`; make limits (line width) configurable            |
| High     | `check_root_entries.py`                                  | `checks/project.py`; parse via `isabelle-layout` if viable |
| High     | `check_build_reelaboration.py`                           | `stats/build.py`; drop session budgets                     |
| High     | `check_no_sorry.py`                                      | only what the common model or `isabelle-linter` lacks      |
| High     | `check_isabelle_ascii.py`, `normalize_isabelle_ascii.py` | `source/symbols.py`; one mapping                           |
| Medium   | `session_graph.py`                                       | concepts only                                              |
| Medium   | `check_thy_prose_refs.py`                                | split generic document safety from heuristics              |
| Medium   | `check_locale_parameters.py`                             | not a default check until corpus-tested                    |

Stay in Voblint: `check_pages_*`, `check_thesis_*`, code-generation API
checks, VIMP generators, thesis/website generation, verification-surface
checks, retired-identifier lists.

Port behavior through tests first. No wholesale copying.

## 9. CLI contract

Exit status: `0` success, `1` check failure or differences found, `2` invalid
invocation or unreadable input. Data on stdout, diagnostics on stderr.

## 10. Package structure

```text
src/isar_tools/
  cli.py
  source/     symbols, regions, theory, model
  formatter/
  checks/
  stats/
  project/
```

Create subpackages when their first code lands. Prefer a few immutable
dataclasses (`TheorySource`, `CommandSpan`, `SourceRegion`, `Project`,
`Session`, `Theory`) over a class hierarchy.

## 11. Quality gates

CI: `pixi install --locked`, `pixi run lint`, `pixi run typecheck`,
`pixi run coverage` on Linux, macOS, and Windows, for the newest Python and
the 3.11 floor.

- 100% line and branch coverage; no large exclusion lists.
- Golden formatter tests (`tests/formatter/input` vs `expected`), checked for
  both `fmt(input) == expected` and `fmt(expected) == expected`.
- Hypothesis property tests for idempotence and token preservation.
- Synthetic project fixtures: multiple sessions, `directories`, imports,
  duplicate names, unreachable theories, qualified names, comments, custom
  keywords.
- Corpus tests (Voblint, Isabelle distribution, selected AFP entries) run as
  integration jobs; nothing large is vendored.

## 12. Milestones

- **M0 scaffold**: pixi, `pyproject.toml`, CLI placeholders, pytest, ruff,
  pyright, lefthook, CI, README, license. Acceptance: `lint`, `coverage`,
  `typecheck`, `isar --help` succeed.
- **M1 source/project model**: dependency decision; ROOT/session discovery;
  lossless `.thy` region model; exact spans for comments and opaque regions.
- **M2 statistics**: `isar stats [sessions|theories|proofs]`, text and JSON.
  Precedes the formatter to exercise the model at low risk.
- **M3 project checks**: ROOT resolution, duplicates, unreachable theories,
  unfinished proofs.
- **M4 formatter MVP**: `fmt`, `--check`, `--diff`; whitespace, blank lines,
  indentation, statement clauses, basic proof layout. Acceptance: idempotence,
  golden tests, no semantic-token change on Voblint, formatted Voblint builds.
- **M5 build statistics**: `isar stats build`.
- **M6 external validation**: Voblint, Isabelle distribution, AFP entries.
  Classify each failure: parser bug, unsupported syntax, formatter bug,
  ambiguous policy, external special case. No project-specific hacks.
- **M7 0.1.0**: GitHub release and PyPI. conda-forge staged recipe and Tools
  Collection only after real external use.

### Status (2026-09)

| Milestone | State                 | Notes                                                                                                                                                                                                   |
| --------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M0        | done                  |                                                                                                                                                                                                         |
| M1        | done                  | Own ROOT parser instead of an `isabelle-layout` adapter (see `PARSER_DECISION.md`).                                                                                                                     |
| M2        | done                  | Also `commands` and `style` views.                                                                                                                                                                      |
| M3        | done                  | Groups `project`, `proofs`, `syntax`, `symbols`; a `syntax` group replaces the planned `document` group (the only precise document check is lexical). Also `isar symbols normalize` and `isar project`. |
| M4        | done except the build | Plus `--max-line-length` wrapping and raise-only default indentation. "Formatted Voblint builds" is open: it needs the round-trip workflow in Voblint's CI.                                             |
| M5        | done                  | Reads one evidence-backed log line format; needs a run on a real log.                                                                                                                                   |
| M6        | partly                | AFP and Voblint corpus runs pass (tokens, idempotence, goal blocks). Isabelle build of formatted sources open.                                                                                          |
| M7        | open                  | Tag `v0.1.0` after the Isabelle round trip passes.                                                                                                                                                      |

Beyond the plan: `isar project hierarchy` (class and locale declarations as
data, for figures such as Voblint's domain tree) and `isar project extract`
(declaration source by name, with a manifest drift check replacing Voblint's
`snippets.py`).

## 13. Design principles

1. Correctness over aggressive formatting; preserve what cannot be formatted
   safely.
2. No semantic rewriting.
3. Idempotence is non-negotiable.
4. One parser and model.
5. Useful without Isabelle.
6. No project-specific hacks; Voblint is the first consumer only.
7. JSON output and exit statuses are public behavior.
8. Integrate rather than duplicate.
9. Conservative formatter.
10. Stay `noarch: python`.

## 14. Verified facts (2026-09)

- PyPI: `isar-tools` is free. `isar` is taken (Equinor robot supervisor), but
  that package installs `isar-start`/`isar-test-print`, not an `isar`
  executable, so there is no command clash.
- `isabelle-layout` 0.2.2 and `isabelle-query` 0.9.2 are pure-Python, MIT,
  `Requires-Python >=3.9`. `isabelle-layout` has no runtime dependencies;
  `isabelle-query` depends only on `isabelle-layout`.
- Unverified: whether either is on conda-forge. `isar-tools` depends on
  neither, so this does not block a conda-forge recipe.
- AFP (Isabelle2025-2 mirror): 1027 ROOTs reached through `ROOTS`, 1057
  sessions, 10342 reached theories; every theory lexes, every goal block closes,
  and formatting preserves tokens and is idempotent.
- Quoted slash entries in `theories` (`"Common/List_Misc"`) are valid (911 in the
  AFP); only the unquoted spelling fails, because it is several tokens.
