# Releasing

The version lives in the git tag. `pyproject.toml` says `0.0.0`, and the
`Build` workflow replaces it with the tag (`v0.1.0` becomes `0.1.0`) before it
builds and publishes.

## Once: set up publishing

1. On PyPI, add a pending trusted publisher (Account settings → Publishing):
   project `isar-tools`, owner `ManuelLerchner`, repository `isar-tools`,
   workflow `build.yml`, environment `pypi`.
2. On GitHub, create the environment `pypi` (Settings → Environments). A
   required reviewer on it makes every publish wait for an approval.

## Each release

1. Check that formatting cannot break a build. `isar fmt` is only tested
   against tokens and idempotence here; the evidence that Isabelle reads the
   same theory is a project that builds after formatting. For Voblint, run its
   manual `isar fmt round trip` workflow with `isar_ref` set to the commit to
   release and confirm it is green.
2. In `CHANGELOG.md`, rename `## Unreleased` to `## X.Y.Z (YYYY-MM-DD)` and
   merge that to `main`.
3. Tag the merge commit and push the tag:

   ```sh
   git tag -a vX.Y.Z -m "isar-tools X.Y.Z"
   git push origin vX.Y.Z
   ```

4. The `Build` workflow builds the wheel and sdist, runs `twine check`, and
   publishes to PyPI. Check the result: `pip install isar-tools==X.Y.Z` and
   `isar --version`.

## conda-forge

The first release goes through
[staged-recipes](https://github.com/conda-forge/staged-recipes): add
`recipes/isar-tools/recipe.yaml` in a fork and open a pull request. The
recipe below is a template in the v1 (`recipe.yaml`) format for a `noarch:
python` package; compare it with the current example in staged-recipes
before submitting, since conda-forge's conventions change. The sha256 is the
one PyPI lists for the sdist.

```yaml
schema_version: 1

context:
  version: "X.Y.Z"
  python_min: "3.11"

package:
  name: isar-tools
  version: ${{ version }}

source:
  url: https://pypi.org/packages/source/i/isar-tools/isar_tools-${{ version }}.tar.gz
  sha256: <sdist sha256 from PyPI>

build:
  noarch: python
  number: 0
  script: ${{ PYTHON }} -m pip install . -vv --no-deps --no-build-isolation
  python:
    entry_points:
      - isar = isar_tools.cli:main

requirements:
  host:
    - python ${{ python_min }}.*
    - hatchling >=1.25
    - pip
  run:
    - python >=${{ python_min }}

tests:
  - python:
      imports:
        - isar_tools
      python_version:
        - ${{ python_min }}.*
        - "*"
      pip_check: true
  - requirements:
      run:
        - python ${{ python_min }}.*
    script:
      - isar --version
      - isar --help
  - files:
      source:
        - tests/
        - pyproject.toml
    requirements:
      run:
        - python ${{ python_min }}.*
        - pytest
        - hypothesis
    script:
      - pytest tests -q -p no:cacheprovider

about:
  homepage: https://github.com/ManuelLerchner/isar-tools
  repository: https://github.com/ManuelLerchner/isar-tools
  license: MIT
  license_file: LICENSE
  summary: Formatter, checks, and statistics for Isabelle/Isar projects, without running Isabelle
  description: |
    isar-tools reads Isabelle theory (.thy) and ROOT files without running
    Isabelle. `isar fmt` formats theories (layout only, idempotent), `isar check`
    reports problems in ROOT files, proofs, syntax, and symbols, `isar stats`
    reports source, proof, and build-log statistics, and `isar project` shows
    sessions, import graphs, class and locale hierarchies, and declarations.

extra:
  recipe-maintainers:
    - ManuelLerchner
```

Once merged, conda-forge creates the `isar-tools-feedstock`; its bot opens a
pull request for every later PyPI release.
