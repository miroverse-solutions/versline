import json
import shutil
import subprocess
import sys
import time
from typing import Optional

import typer
from rich.console import Console

from versline import __version__
from versline.userconfig import user_config_dir, user_env_path

console = Console()

REPO = "miroverse-solutions/versline"
# Shared with the bridge (versline.userenv); the old private names stay for existing callers.
from versline.userenv import DEFAULT_MODELS, PROVIDERS  # noqa: E402
from versline.userenv import mask as _mask  # noqa: E402
from versline.userenv import read_env as _read_env  # noqa: E402


def init_command():
    """Interactive first-time setup: choose a provider and save your API key."""
    path = user_env_path()
    values = _read_env(path)

    console.print(f"[bold]Versline setup[/bold]  (settings file: {path})")
    provider = typer.prompt(
        f"Provider ({', '.join(PROVIDERS)})", default=values.get("VERSLINE_LLM_PROVIDER", "Google")
    )
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider '{provider}'.[/red]")
        raise typer.Exit(1)

    api_key = typer.prompt("API key", default=values.get("VERSLINE_LLM_API_KEY", ""), hide_input=True, show_default=False)
    model = typer.prompt("Model", default=values.get("VERSLINE_LLM_MODEL") or DEFAULT_MODELS[provider])
    values.update(
        VERSLINE_LLM_PROVIDER=provider,
        VERSLINE_LLM_API_KEY=api_key,
        VERSLINE_LLM_MODEL=model,
    )
    if provider == "OpenAICompatible":
        values["VERSLINE_LLM_API_ENDPOINT"] = typer.prompt(
            "API endpoint URL", default=values.get("VERSLINE_LLM_API_ENDPOINT", "")
        )
    proxy = typer.prompt(
        "Proxy URL (leave empty for none)", default=values.get("VERSLINE_LLM_PROXY", ""), show_default=False
    )
    if proxy:
        values["VERSLINE_LLM_PROXY"] = proxy
    else:
        values.pop("VERSLINE_LLM_PROXY", None)

    from versline.userenv import write_env

    write_env(values, path)
    console.print("[green]Saved.[/green] You can now run, for example: versline transcribe FILE")


def config_command(
    show: bool = typer.Option(True, "--show/--path", help="Show saved settings (keys masked), or only print the file path"),
):
    """Show the saved per-user settings."""
    path = user_env_path()
    if not show:
        typer.echo(str(path))
        return
    values = _read_env(path)
    if not values:
        console.print(f"No settings saved yet at {path}. Run: [bold]versline init[/bold]")
        return
    console.print(f"[dim]{path}[/dim]")
    for key, value in values.items():
        console.print(f"{key}={_mask(key, value)}", markup=False, highlight=False)


def _latest_release(timeout: float = 2.0) -> dict:
    """Return {"tag": str, "wheel_url": str | None} for the latest published release."""
    from versline.services.releases import fetch_release

    release = fetch_release(REPO, timeout=timeout)
    wheel_url = next((url for name, url in release["assets"].items() if name.endswith(".whl")), None)
    return {"tag": release["tag"], "wheel_url": wheel_url}


def _version_tuple(tag: str):
    from versline.services.releases import version_tuple

    return version_tuple(tag)


def update_command():
    """Update Versline to the latest release."""
    console.print(f"Current version: {__version__}")
    try:
        release = _latest_release(timeout=15)
    except Exception as exc:
        console.print(f"[red]Could not check for updates:[/red] {exc}")
        raise typer.Exit(1)

    tag, wheel_url = release["tag"], release["wheel_url"]
    if not tag or not wheel_url:
        console.print("[red]No published release with a .whl file was found.[/red]")
        raise typer.Exit(1)
    if _version_tuple(tag) <= _version_tuple(__version__):
        console.print("[green]You already have the latest version.[/green]")
        return

    console.print(f"Updating to {tag}...")
    if sys.platform == "win32":
        # Windows cannot replace versline.exe while it is running, so hand over to the
        # installer in a new window that starts after this process exits.
        command = (
            "Start-Sleep -Seconds 2; "
            f"irm https://raw.githubusercontent.com/{REPO}/main/install.ps1 | iex; "
            "Read-Host 'Press Enter to close'"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", command],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        console.print("A new window will finish the update. Then open a new terminal.")
        return

    uv = shutil.which("uv")
    if not uv:
        console.print("[red]uv was not found.[/red] Re-run the install command from the README to update.")
        raise typer.Exit(1)
    result = subprocess.run([uv, "tool", "install", "--force", "--python", "3.12", f"versline[export] @ {wheel_url}"])
    if result.returncode != 0:
        raise typer.Exit(result.returncode)
    console.print("[green]Done.[/green] Run 'versline --version' to confirm.")


def maybe_notify_update() -> None:
    """Print a one-line notice if a newer release exists. Checks at most once a day; never raises."""
    try:
        if not sys.stderr.isatty():
            return
        stamp = user_config_dir() / "last_update_check.json"
        now = time.time()
        if stamp.is_file():
            data = json.loads(stamp.read_text(encoding="utf-8"))
            if now - data.get("checked", 0) < 86400:
                return
        user_config_dir().mkdir(parents=True, exist_ok=True)
        tag = _latest_release()["tag"]
        stamp.write_text(json.dumps({"checked": now, "tag": tag}), encoding="utf-8")
        if tag and _version_tuple(tag) > _version_tuple(__version__):
            console.print(
                f"[yellow]A new version ({tag}) is available. Run: versline update[/yellow]",
                highlight=False,
            )
    except Exception:
        return
