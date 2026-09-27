# Changelog

## Unreleased

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
