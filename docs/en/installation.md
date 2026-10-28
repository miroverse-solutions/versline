# Installation

[Index](index.md) · **English** · [فارسی](../fa/installation.md)

## End users

### Windows (recommended)

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
```

The script downloads `versline-windows-x64.zip` from the latest GitHub release (about 150 MB, using `curl.exe` for a visible progress bar, falling back to `Invoke-WebRequest`), extracts it to `%LOCALAPPDATA%\Versline` (replacing any previous install, with zip-slip path validation) and adds that folder to your user `PATH`. It is self-contained: **no Python, uv or PyPI access is needed**, and ffmpeg is bundled.

### macOS / Linux

```sh
curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh
```

The script installs [uv](https://docs.astral.sh/uv/) if missing, then runs `uv tool install --force --python 3.12 <wheel>` with the wheel from the latest release, and `uv tool update-shell`.

### After installing

Close the terminal and open a **new** one, then:

```sh
versline --version
versline init      # choose provider, API key, model (once)
```

ffmpeg is resolved automatically (see [Configuration](configuration.md#media)). On the Windows console Persian text may look broken; open the output files in an editor instead.

### Update

```sh
versline update
```

Versline also checks GitHub for a newer release at most once a day (only in an interactive terminal) and prints a notice. On Windows, `update` opens a new PowerShell window that re-runs `install.ps1`; elsewhere it runs `uv tool install --force` (requires `uv`).

### Uninstall

- Windows: delete `%LOCALAPPDATA%\Versline` and remove it from your user `PATH`.
- macOS / Linux: `uv tool uninstall versline`.
- Optionally delete the per-user config folder (see [Configuration](configuration.md#where-settings-live)).

## From source

```sh
git clone https://github.com/miroverse-solutions/versline.git
cd versline
pip install .
```

Requires Python 3.9+ (releases are built and tested with Python 3.12).

## Development setup

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # same as: make dev
make test                    # python -m pytest tests -q
```

## Build a wheel

```sh
make build                   # python -m build, output in dist/
pip install dist/versline-*.whl
```

## Shell completion

```sh
versline --install-completion
```

## Releasing (maintainers)

`make release` runs the tests, requires a clean and pushed tree, then triggers the *Manual Draft Release* GitHub Actions workflow (`make release-draft` creates a draft). The workflow tests on Ubuntu/Windows/macOS, builds the Windows PyInstaller bundle (with ffmpeg) and publishes the wheel, sdist and Windows zip under tag `vX.Y.Z` taken from `pyproject.toml`.
