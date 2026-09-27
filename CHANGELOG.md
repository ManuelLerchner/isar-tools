# Changelog

## Unreleased

- Source model: lossless outer-syntax lexer, Isabelle symbol table, theory headers,
  command segmentation with per-theory keyword tables, and goal blocks.
- Project model: ROOT parser with positioned diagnostics, `ROOTS` discovery, theory and
  import resolution, reachability.
- Opt-in corpus tests (`pixi run corpus` with `ISAR_CORPUS`).
- Repository scaffold: pixi environment, package skeleton, `isar` CLI with
  placeholder commands, tests, lint, type checking, and CI.
