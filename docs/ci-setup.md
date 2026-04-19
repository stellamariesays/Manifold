# CI Setup

GitHub Actions CI is defined in `.github/workflows/ci.yml`.

## Applying CI

The workflow file can't be pushed with a PAT that lacks `workflow` scope.
To apply it, a repo admin with a token that has `workflow` scope should create
`.github/workflows/ci.yml` with the content below, or approve this PR from the
GitHub web UI after granting that scope.

## Workflow content

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .
          pip install pytest

      - name: Run tests
        run: |
          python -m pytest tests/ \
            -m "not integration" \
            -q
```

## What it does

- Triggers on push to `main` and on PRs targeting `main`
- Matrix: `ubuntu-latest` × Python `3.12`
- Installs the package with `pip install -e .` + `pytest`
- Runs all tests except `integration`-marked tests (which require federation setup)
