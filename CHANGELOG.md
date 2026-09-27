# Changelog

## Unreleased

- A directory argument skips subdirectories that have their own `ROOT` or `ROOTS` but
  hold none of the project's sessions (a vendored submodule not listed in `ROOTS`), with
  a note on stderr; pass such a directory with `-d` to resolve against it. Before, its
  theories were checked, formatted, and counted as loose theories of the project.
- Theory ownership no longer depends on how the ROOT files were found. Sessions claim
  theories ancestors first (parents and `sessions` entries before the sessions built on
  them), and a session never claims a theory from another session's directories through
  an import. `isar project sessions .` (reading `ROOTS`) and `isar project sessions src`
  (searching for `ROOT` files) now agree on Voblint, where one theory switched sessions.

## 0.1.1 (2026-09-27)

- A directory argument no longer includes the theories of `-d` directories nested
  in it. An AFP or a vendored submodule inside a project provides sessions to resolve
  against; `isar check .` reported their `sorry` and `oops`, and `isar fmt .` would
  have rewritten them.

## 0.1.0 (2026-09-27)

First release.

- Packaging: the sdist holds sources, tests, and documentation only (no lock files or
  demo recording); README links are absolute, so they work on PyPI.
  `docs/RELEASING.md` describes a release, including the conda-forge recipe.
- `-d DIR` must name an existing directory (exit status 2 otherwise), as with
  `isabelle build -d`. Before, a mistyped `-d` was ignored, and commands of that
  directory were silently read as part of the previous command.
- `isar project names`: named declarations with qualified name (`Theory.locale.name`),
  kind, command, session, location, and docstring (a directly preceding `text` block), as
  text, JSON, CSV, or a Markdown index grouped by session and theory. `--kind` filters;
  `--name` (base or exact qualified name) exits 1 for a name that declares nothing and
  suggests the qualified names that exist. Replaces Voblint's
  `extract_definitions.py --dump` and `check_theory_anchors.py`.
- `isar ... | head` no longer prints a `BrokenPipeError` traceback.
- `isar project extract NAME...`: the source of a declaration (command and, for a goal,
  its proof), found by `name`, `locale.name`, `Theory.name`, or `Theory.locale.name`; a
  name must identify exactly one declaration. `--manifest TOML --out DIR --write|--check`
  keeps quoted declarations in a document in sync with the theories (the format of
  Voblint's `thesis/shared/snippets.toml`).
- `isar check docs`: opt-in documentation-coverage group, ported from Voblint's
  `extract_definitions.py --lint`. `undocumented-theory` (no `text` before the first
  declaration), `undocumented-heading` (no `text` right after or before a heading),
  `undocumented-locale` and `undocumented-class` (no `text` right before the declaration).
  `(* *)` comments, formal comments, and `text_raw` do not count as documentation.
- `isar check locales` (opt-in group, code `locale-free-variable`): identifiers in the
  terms of `locale` and unnamed `context` headers that are no parameter (own, `for`
  clause, `defines`, or inherited from parent locales through imports), not bound in the
  term, and not used anywhere else in the project or its `-d` imports; Isabelle would
  generalize over them. Heuristic filter: at least four characters and an underscore.
  `--allow NAME` (repeatable). Ported from Voblint's `check_locale_parameters.py`.
- `isar project hierarchy` model: declarations also record `for` clause parameters,
  `defines`, and term tokens; `context` headers parse too; `opening` ends a locale
  expression.
- Lexer: `\<in>`, `\<le>`, and other two-letter symbols are no longer identifier letters
  (only doubled letters such as `\<AA>` are), and `\<^sup>`/`\<^bold>` no longer continue
  an identifier.
- `isar project hierarchy`: class and locale declarations (parents, fixes with type and
  notation, assumes, parameter sorts) as text, JSON, or DOT; `--root` follows parents
  through imports, including `-d` directories, and reports unresolved names.
- Unqualified imports of global theory names (`Main`) resolve through the parent
  session chain.
- `isar stats build BUILD_LOG`: where theory elaboration time went in an `isabelle build -v`
  log. Per building session: theories elaborated, cpu seconds, and the share spent on
  theories owned by other sessions; theories elaborated more than once with the time
  wasted (`--top N`); `--budget SESSION=N` (repeatable) exits 1 when SESSION's theories
  are elaborated inside other sessions more than N times. Reads only the line format
  `SESSION: theory OWNER.THEORY 100% (Ns cumulated time)`; a log without such lines, or one
  in which a session elaborates a theory twice, is exit status 2 (`--allow-empty` accepts
  an incremental build that rebuilt nothing). `build` is now a view
  name, so a directory called `build` needs `isar stats ./build`.
- `isar check` prints a summary line (`2 findings: 1 missing-theory, ...`) and colours
  findings on a terminal; `fmt --diff` and `symbols normalize --diff` colour their diffs.
  `--color auto|always|never`; `NO_COLOR` is honoured. Finding messages are shorter.
- README demo GIF recorded by VHS from `docs/demo/demo.tape` (`pixi run demo`, in a
  separate `demo` environment). It shows `isar fmt --diff`; `pixi run demo-check` runs the
  tape's commands without recording and checks their exit status.
- Source model: lossless outer-syntax lexer, Isabelle symbol table, theory headers,
  command segmentation with per-theory keyword tables, and goal blocks.
- Project model: ROOT parser with positioned diagnostics, `ROOTS` discovery, theory and
  import resolution, reachability.
- `isar stats` with views `summary`, `sessions`, `theories`, `proofs`, `commands`, and
  `style`, in text, Markdown, JSON, and CSV.
- `isar check` with groups `project`, `proofs`, `syntax` (default) and `symbols`; stable
  finding codes, `--ignore`, text/JSON/CSV output, exit status 1 on findings.
- `isar symbols normalize` (ASCII or Unicode spelling; `--check`, `--diff`).
- `isar project sessions|theories|graph` (graph as text, JSON, or DOT).
- `-d DIR` on `stats`, `check`, and `project`: sessions of DIR resolve imports and
  commands, like `isabelle build -d`.
- Source files are read and written byte-exactly, so CRLF line endings survive.
- `isar fmt`: conservative formatter (indentation from proof structure, trailing
  whitespace, blank lines); `--check`, `--diff`, `--normalize`, stdin via `-`. Changes
  only layout, by construction and by test.
- Opt-in corpus tests (`pixi run corpus` with `ISAR_CORPUS`).
- Repository scaffold: pixi environment, package skeleton, `isar` CLI with
  placeholder commands, tests, lint, type checking, and CI.
