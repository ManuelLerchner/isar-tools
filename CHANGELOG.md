# Changelog

## Unreleased

- `isar check unused` (opt-in, heuristic): `unused-lemma` reports a named fact
  nothing in the project cites. Facts with an attribute such as `[simp]` count as
  used; `--allow` keeps a main result cited only elsewhere. `redundant-import` reports
  an import another import reaches already; `unused-import` (heuristic) one of which
  the theory names nothing and that has no instances, notation, ML, or simp rules.
  `unused-assumption` reports a named locale or class assumption no proof cites.
- `isar check methods` (opt-in): `empty-modifier` reports a method modifier with
  nothing after it, as in `by (simp add:)`; `duplicate-fact` a fact listed twice after
  one modifier.
- `isar check notation` (opt-in, heuristic): `spelled-out-notation` reports a
  constant written out in a term where the project gave it a short form: a mixfix on
  its declaration, a `notation` command, or `adhoc_overloading`. Bundles, locales, and
  anonymous `context` blocks scope a short form; `--allow` accepts a constant.
  `spelled-out-abbreviation` reports a term that is the right-hand side of an
  `abbreviation`.
- `isar check`: a `(* isar-ignore *)` comment silences the findings on its line, or
  on the next line when it stands alone; `(* isar-ignore: CODE, ... *)` silences only
  those codes.

## 0.4.0 (2026-10-01)

- `isar project notation TOML`: the symbols a project's declarations introduce, as
  JSON. A manifest lists declarations (`[notation.KEY]` with `name`, `args`, `file`);
  for each, the output gives its shape (theory-level constant, class parameter, record
  field, locale parameter, or abbreviation in a locale), scope, location, mixfix, the
  `symbol` its mixfix writes with the `_` slots filled by `args` (and as `unicode`),
  the print mode (`abbreviation (input)` is never printed back), an abbreviation's two
  sides, and the HTML anchors of the declaration and its owner. Other shapes fail with
  their location. With `--browser-info DIR`, every anchor must exist; with `--check`,
  the JSON in `--out` must be current.
- `isar project anchors --browser-info DIR [NAME...]`: the anchors of a built HTML
  presentation, HOL and library sessions included, listed or found by name (a dotted
  suffix or `Theory.name`, with `|kind` or `--kind`). A name that matches several
  definitions is an error listing them; `--prefer PREFIX` (repeatable, first is best)
  keeps those on pages below a prefix. `project notation --browser-info` looks up
  there the anchors the sources cannot give, such as an owner from HOL, and also takes
  `--prefer`.

## 0.3.0 (2026-09-30)

- `isar project names` lists the constructors, discriminators, and selectors of a
  datatype or codatatype as constants named in the type (`t.C`, `t.sel`), and the
  constants of `consts`.
- `isar project extract --statement`: the statement without its proof, and a locale,
  class, or instantiation without its `begin`. A manifest entry takes `proof = true` or
  `false` to override it, and `name` to extract something other than its key.
- `isar project extract` finds class instances by `type :: class` and qualified
  interpretations by their qualifier.
- `isar project extract` also finds declarations of `-d` directories when the project
  has none of the name, and a manifest `file` may be `~~/src/HOL/...`, read below
  `ISABELLE_HOME` (skipped with a note when it is unset) and printed back as `~~/`. A
  declaration wins over parameters, fields, and constructors of the same name, so
  `extract bot` gives HOL's `class bot`.
- `isar project names FILE.thy ...` lists the declarations of those theory files only,
  such as a few of HOL's without reading every HOL session.
- `isar project instances`: every `instantiation`, `instance t :: c`, `interpretation`,
  and `global_interpretation` of the project, with its name (`t :: c` or the qualifier),
  its class or locale, and the locale's arguments.
- `isar project names --statements` (JSON and CSV): a `statement` column with each
  declaration's statement as `extract --statement` prints it, for every lemma in one call.
- `isar project names` JSON and CSV: `mixfix`, `notation`, and `mode` (`input` for
  `abbreviation (input)`) of constants, record fields, constructors, and locale
  parameters. The parameters of a locale's `for` clause are listed as constants of the
  locale (command `for`), and `hierarchy --format json` has them as `for_fixes`. A
  mixfix keeps its spacing as written (`[51, 51] 50`, was `[ 51 , 51 ] 50`).
- `isar check`: `theory-path` in the `project` group, a quoted `theories` entry with a
  `/` (`theories "generated/Foo"`), which Isabelle does not load. The fix is
  `directories "generated"` and `theories Foo`.
- `isar check retired`: identifiers the project lists as removed (`check.retired`,
  `check.retired-file`, `--retired`, `--retired-file`) that appear again outside
  `(* *)` comments, also as `foo_def` or `foo_axioms`. A deleted constant cited in an
  assumption is otherwise a free variable, and the build does not notice.
- `isar check prose`: `prose-reference`, a plain `\<open>name\<close>` cartouche in
  document text that names nothing the project declares or uses (Isabelle checks
  antiquotations, not these), and `prose-underscore`, a raw `_` in document prose,
  which LaTeX rejects.
- `isar project names` JSON and CSV: `anchor`, the id Isabelle's HTML presentation
  gives the definition (`Theory.loc.name|fact`), and `url`, its page and anchor below
  browser_info (`Chapter/Session/Theory.html#...`).
- `isar check links FILE...`: links from HTML and Markdown into Isabelle's HTML
  theories. With `--browser-info DIR` (and `--link-base URL`), the page and anchor must
  exist (`broken-link`, `broken-anchor`); without a build, an anchor must spell the name
  with the scope the theory declares it in (`anchor-name`).
- `isar project graph --layers`: sessions in strata, each one layer above the highest
  session it rests on (parent, `sessions` entries, sessions its theories import),
  including the `-d` sessions the project rests on. Text lists what each session rests
  on, JSON adds `layers` and `imports` edges, DOT puts each layer in one rank.

## 0.2.0 (2026-09-27)

- Install from conda-forge: `pixi global install isar-tools` or
  `conda install -c conda-forge isar-tools`.
- `isar project names` lists locale and class parameters (`L.x`, `c_class.x`), named
  locale assumptions (`L.a`), and record fields (`r.field`). `--derived` adds derived
  facts (`f_def`, `f.simps`, `P.intros` and named rules, `t.inject`, `L_def`, `L.intro`,
  ...) and the facts of qualified interpretations (`q.fact`), with a `derived_from`
  column. On Voblint, 112 of its 113 site anchors into rendered theories now name a
  listed fact or constant; the last is in a session outside the project.
- `isar check`: `theory-name` (the header names a theory other than the file, or a
  qualified one) and `invalid-utf8` in the default `syntax` group; opt-in groups
  `hygiene` (`tab`, `carriage-return`, `bidi-control`, `reserved-file-name`, after
  Isabelle's `check_sources`) and `leftovers` (`proof-search`, `counterexample-search`
  without `expect`, `diagnostic-command`, after isabelle-linter's rules of those names).
  A theory that is not UTF-8 no longer stops `isar check`.
- Theory headers with a document tag (`theory %invisible All`) are read correctly; the
  tag was taken for the theory name.
- `isar stats commands --by theory`: command counts per theory (session, theory,
  command, count, path); `--by session` stays the default.
- `isar stats build --default-budget N --project DIR`: every library session without its
  own `--budget` is held to N elaborations inside other sessions, where library means not
  a session of DIR. A new library dependency that gets re-elaborated then fails the check.
- Commands of AFP entries are recognised without an AFP checkout: a table generated
  from the AFP (revision cfdc3d77e, 2026-09-02) lists the commands each AFP session
  makes visible to theories importing it, e.g. `derive` from `Deriving`. `-d` still
  adds what a newer AFP declares. Regenerate with `scripts/gen_afp_commands.py`; the
  corpus tests fail when the table is stale.
- `--exclude GLOB` for `fmt`, `check`, and `stats`: leave out matching files (`**`
  spans directories), also when named on the command line.
- Configuration file: `[tool.isar]` in `pyproject.toml`, or `isar.toml`, found upward
  from the working directory. `include` (`-d` directories, `$VAR` expanded, absent ones
  skipped with a note), `exclude`, and defaults for `fmt` (`max-line-length`, `indent`,
  `max-blank-lines`, `normalize`), `check` (`groups`, `ignore`, `allow`), and `stats`
  (`max-line-length`, `watch`). Command-line options take precedence.
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
