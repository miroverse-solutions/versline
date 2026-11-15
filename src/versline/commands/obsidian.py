"""`versline obsidian`: install or update the Versobs plugin in an Obsidian vault (downloaded from its GitHub releases)."""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Install or update the Versobs Obsidian plugin (from github.com/miroverse-solutions/versobs).")
console = Console()

VAULT_HELP = "Vault folder (contains .obsidian). Default: the most recently opened vault."


def _fail(exc: Exception) -> None:
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(1)


@app.command("vaults")
def vaults():
    """List the vaults Obsidian knows on this computer."""
    from versline.services.obsidian_plugin import known_vaults

    rows = known_vaults()
    if not rows:
        console.print("No vaults found. Open your vault in Obsidian once, or pass --vault PATH to install.")
        return
    table = Table(title="Obsidian vaults")
    for column in ("Vault", "Path", "Plugin"):
        table.add_column(column)
    for row in rows:
        installed = row["installed"] or ("-" if row["exists"] else "missing folder")
        table.add_row(row["name"] + (" (open)" if row["open"] else ""), row["path"], installed)
    console.print(table)


@app.command("install")
def install(
    vault: Optional[Path] = typer.Option(None, "--vault", "-V", help=VAULT_HELP),
    version: Optional[str] = typer.Option(None, "--version", help="Install this release tag instead of the latest"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy for GitHub (default: VERSLINE_LLM_PROXY)"),
    force: bool = typer.Option(False, "--force", "-f", help="Reinstall even if up to date"),
):
    """Install the plugin, or update it to the latest release. Its settings (data.json) are kept."""
    from versline.services.obsidian_plugin import PluginInstallError, install_plugin

    try:
        with console.status("Downloading the latest Versobs release..."):
            result = install_plugin(vault, tag=version, proxy=proxy, force=force)
    except PluginInstallError as exc:
        _fail(exc)
    except Exception as exc:  # network errors
        _fail(RuntimeError(f"Could not install the plugin: {exc}"))

    if result.status == "up-to-date":
        console.print(f"[green]Versobs {result.version} is already up to date[/green] in {result.vault}")
        return
    if result.status == "installed":
        console.print(f"[green]Installed Versobs {result.version}[/green] in {result.plugin_dir}")
        console.print("Next: in Obsidian open Settings → Community plugins, turn off Restricted mode if asked, "
                      "and enable [bold]Versobs[/bold].")
    else:
        previous = f" (was {result.previous})" if result.previous else ""
        console.print(f"[green]Updated Versobs to {result.version}[/green]{previous}")
        console.print("Reload Obsidian (or disable and re-enable Versobs) to load the new version.")


@app.command("status")
def status(
    vault: Optional[Path] = typer.Option(None, "--vault", "-V", help=VAULT_HELP),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy for GitHub"),
):
    """Show the installed and the latest plugin version."""
    from versline.services.obsidian_plugin import PluginInstallError, plugin_status

    try:
        info = plugin_status(vault, proxy=proxy)
    except PluginInstallError as exc:
        _fail(exc)
    console.print(f"Vault:     {info['vault']}")
    console.print(f"Installed: {info['installed'] or 'not installed'}")
    if info["error"]:
        console.print(f"Latest:    [yellow]unknown ({info['error']})[/yellow]")
    else:
        console.print(f"Latest:    {info['latest']}")
        if info["update_available"]:
            console.print("Run: [bold]versline obsidian install[/bold]")
