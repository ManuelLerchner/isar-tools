# Changelog

## Unreleased

- `isar project hierarchy`: class and locale declarations (parents, fixes with type and
  notation, assumes, parameter sorts) as text, JSON, or DOT; `--root` follows parents
  through imports, including `-d` directories, and reports unresolved names.
- Unqualified imports of global theory names (`Main`) resolve through the parent
  session chain.
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
