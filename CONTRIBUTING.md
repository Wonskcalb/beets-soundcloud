# Contributing to beets-soundcloud

Thanks for taking the time to contribute!

## Getting started

```bash
git clone https://github.com/YOUR_USERNAME/beets-soundcloud
cd beets-soundcloud
uv sync --dev
uv run pre-commit install
```

## Project structure

```
beets-soundcloud/
├── beetsplug/
│   └── soundcloud.py   # the entire plugin
├── tests/
│   └── test_soundcloud.py
├── pyproject.toml
├── CHANGELOG.md
└── README.md
```

`beetsplug` is a [namespace package](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/) shared with beets and other third-party plugins — do **not** add an `__init__.py` to it.

## Running tests

```bash
uv run pytest
```

Every test must have a Gherkin-style docstring (`Given` / `When` / `Then`) describing what it verifies:

```python
def test_strips_matching_prefix(self):
    """
    Given a title with a leading "Artist - Title" prefix matching the artist
    When stripping the artist prefix
    Then the prefix and separator are removed
    """
    ...
```

Use generic placeholder names (e.g. `Test Artist`, `Test Track`) in test data instead of real artist or track names.

## Code style

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
uv run ruff check .
uv run ruff format .
```

Both are enforced in CI. The `pre-commit` hooks installed above run Ruff (and basic whitespace/YAML/TOML checks) automatically on `git commit`; run them on demand with:

```bash
uv run pre-commit run --all-files
```

## Submitting changes

1. Fork the repository and create a branch: `git checkout -b my-feature`
2. Make your changes and add or update tests where relevant
3. Run `uv run pytest` and `uv run ruff check .` — both must pass
4. Update `CHANGELOG.md` under `[Unreleased]`
5. Open a pull request with a clear description of what changed and why

## Reporting issues

Use the GitHub issue templates. For bugs, include:
- beets version (`beet version`)
- Python version (`python --version`)
- Relevant lines from beets log output (`beet -vv import ...`)
- Steps to reproduce (without sharing your credentials)

## Security

Do **not** open a public issue for security vulnerabilities. Instead, open a [GitHub Security Advisory](https://docs.github.com/en/code-security/security-advisories) on the repository.
