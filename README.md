# isar-tools

Source tooling for Isabelle/Isar projects: a formatter, project and source
checks, and statistics. Pure Python. Works on `.thy` and `ROOT` files without
running Isabelle.

Status: pre-alpha. All commands are implemented. See
[`docs/PLAN.md`](docs/PLAN.md) for scope and milestones.

## Commands (planned)

```text
isar fmt       Format Isabelle/Isar source files
isar check     Check project and source hygiene
isar stats     Report source, proof, and build statistics
isar project   Inspect Isabelle project structure
isar symbols   Inspect or normalize Isabelle symbols
```

Exit status: `0` success, `1` check failure or differences found, `2` invalid
invocation or unreadable input. Data goes to stdout, diagnostics to stderr.

## Development

Requires [pixi](https://pixi.sh).

```sh
pixi run pre-commit-install  # git hooks
pixi run test
pixi run coverage            # 100% line and branch coverage required
pixi run typecheck           # pyright, strict
pixi run lint
pixi run isar --help
```

## License

MIT
