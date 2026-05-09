# Publishing Claudible to PyPI

## Goal

Users install with:
```bash
pipx install claudible    # recommended (isolated env)
uv tool install claudible  # alternative
pip install claudible      # works too
```

Then run `claudible install` for the interactive setup wizard (system deps, VOSK model, nerd-dictation, hooks, systemd).

Uninstall with `claudible uninstall` + `pipx uninstall claudible`.

---

## 1. PyPI Account Setup

1. Register at https://pypi.org/account/register/
2. Enable 2FA (required for new accounts)
3. Create an API token: Account Settings → API tokens → "Add API token"
   - Scope: "Entire account" for first publish, then restrict to `claudible` project after
4. Save the token (starts with `pypi-`)

Optional: register on https://test.pypi.org first to test the flow.

## 2. pyproject.toml Updates

The current `pyproject.toml` is mostly ready. Add these fields:

```toml
[project]
# ... existing fields ...

# Add project URLs (shows on PyPI sidebar)
[project.urls]
Homepage = "https://github.com/JayTitus/claudible"
Documentation = "https://github.com/JayTitus/claudible#readme"
Repository = "https://github.com/JayTitus/claudible"
Issues = "https://github.com/JayTitus/claudible/issues"
Changelog = "https://github.com/JayTitus/claudible/releases"
```

Also verify:
- `name = "claudible"` — check https://pypi.org/project/claudible/ is not taken
- `version = "0.1.0"` — bump for each release
- `readme = "README.md"` — this becomes the PyPI page
- `license = "MIT"` — already set

## 3. Build and Test Locally

```bash
cd ~/Source/claudible

# Build the distribution
uv build
# Creates: dist/claudible-0.1.0-py3-none-any.whl
#          dist/claudible-0.1.0.tar.gz

# Verify the wheel contents
unzip -l dist/claudible-0.1.0-py3-none-any.whl

# Test install in a fresh venv
uv venv /tmp/test-claudible --python 3.11
uv pip install --python /tmp/test-claudible dist/claudible-0.1.0-py3-none-any.whl
/tmp/test-claudible/bin/claudible --help
rm -rf /tmp/test-claudible
```

## 4. Test Publish (test.pypi.org)

```bash
# First time: test on test.pypi.org
uv publish --publish-url https://test.pypi.org/legacy/ --token YOUR_TEST_PYPI_TOKEN

# Verify install from test PyPI
pipx install --index-url https://test.pypi.org/simple/ claudible
```

## 5. Publish to PyPI

```bash
# Real publish
uv publish --token YOUR_PYPI_TOKEN

# Verify
pipx install claudible
claudible --help
```

## 6. GitHub Actions: Auto-Publish on Release

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

permissions:
  id-token: write  # Required for trusted publishing (no API token needed)

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi  # Optional: require manual approval

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Build package
        run: uv build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # Uses trusted publishing — no token needed if configured on PyPI
```

### Setting Up Trusted Publishing (Recommended)

Trusted publishing eliminates API tokens entirely. PyPI verifies the GitHub Actions identity.

1. Go to https://pypi.org/manage/project/claudible/settings/publishing/ (after first manual publish)
2. Add a new publisher:
   - Owner: `JayTitus`
   - Repository: `claudible`
   - Workflow: `publish.yml`
   - Environment: `pypi` (or leave blank)
3. Remove your API token — you won't need it anymore

### Alternative: Token-Based Publishing

If you prefer tokens over trusted publishing:

```yaml
      - name: Publish to PyPI
        run: uv publish --token ${{ secrets.PYPI_TOKEN }}
```

Add `PYPI_TOKEN` to GitHub repo → Settings → Secrets → Actions.

## 7. GitHub Actions: Lint and Test on PR

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv run ruff check src/
      - run: uv run ruff format --check src/

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          python-version: ${{ matrix.python }}
      - run: uv sync --extra dev
      - run: uv run pytest tests/ -v
```

## 8. Release Workflow

When ready to release a new version:

```bash
# 1. Bump version in pyproject.toml
#    version = "0.2.0"

# 2. Commit
git add pyproject.toml
git commit -m "Release v0.2.0"
git push

# 3. Create GitHub release (triggers publish workflow)
gh release create v0.2.0 --title "v0.2.0" --generate-notes
```

The GitHub Action builds and publishes to PyPI automatically.

## 9. Versioning Strategy

Use semantic versioning:
- `0.x.y` — pre-1.0, breaking changes allowed on minor bumps
- `1.0.0` — first stable release (when install wizard is solid + STT/TTS stable)
- Bump patch for bug fixes, minor for features, major for breaking changes

Consider using `hatch-vcs` to derive version from git tags automatically:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]

[tool.hatch.version]
source = "vcs"
```

Then remove `version = "0.1.0"` from `[project]` and add:
```toml
[project]
dynamic = ["version"]
```

Version is derived from `git describe --tags`.

## 10. Checklist Before First Publish

- [ ] Verify `claudible` name is available on PyPI
- [ ] Add `[project.urls]` to pyproject.toml
- [ ] Clean up README.md (this becomes the PyPI landing page)
- [ ] Ensure `claudible install` and `claudible uninstall` work from a fresh pip install
- [ ] Run `uv build` and inspect the wheel (no missing files, no junk)
- [ ] Verify voice .wav files are included (`tool.hatch.build.artifacts`)
- [ ] Test publish to test.pypi.org first
- [ ] Set up GitHub Actions workflow
- [ ] Create first GitHub release → auto-publish to PyPI
- [ ] After first publish, set up trusted publishing on PyPI
- [ ] Add PyPI badge to README: `[![PyPI](https://img.shields.io/pypi/v/claudible)](https://pypi.org/project/claudible/)`

## Files to Create

| File | Purpose |
|------|---------|
| `.github/workflows/publish.yml` | Auto-publish to PyPI on GitHub release |
| `.github/workflows/ci.yml` | Lint + test on push/PR |
| `CHANGELOG.md` | Optional, or use GitHub release notes |

## Summary

The full user experience:

```bash
# Install
pipx install claudible        # from PyPI
claudible install              # interactive wizard for system deps

# Use
claudible start                # or: systemctl --user start claudible

# Update
pipx upgrade claudible

# Uninstall
claudible uninstall            # remove hooks, systemd, etc.
pipx uninstall claudible       # remove the package
```
