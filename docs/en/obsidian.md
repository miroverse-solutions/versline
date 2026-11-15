# Obsidian plugin (Versobs)

[Index](index.md) · **English** · [فارسی](../fa/obsidian.md)

**Versobs** is an Obsidian plugin that brings Versline's tools into Obsidian: transcription, translation, summaries, questions and flashcards, qualitative coding, research writing, slides, Word/PDF export, Telegram archives and folder reports. Versline does the work in the background, so **Versline must be installed** (see [Installation](installation.md)) and set up once with `versline init`. The plugin also has a settings page for provider, model, API key and proxy.

The plugin lives in its own repository, [miroverse-solutions/versobs](https://github.com/miroverse-solutions/versobs), and is not bundled with Versline. Versline only downloads its latest release for you.

## Install or update the plugin

```sh
versline obsidian vaults                       # the vaults Obsidian knows on this computer
versline obsidian install                      # install into the most recently opened vault
versline obsidian install --vault ~/Notes      # or into a specific vault
versline obsidian status --vault ~/Notes       # installed vs. latest version
```

`install` downloads `manifest.json`, `main.js` and `styles.css` from the latest release into `<vault>/.obsidian/plugins/versobs/`. Only those files are replaced, so the plugin's settings (`data.json`) are kept. Running it again updates the plugin, or reports that it is already up to date. Options: `--version TAG` installs a specific release, `--force` reinstalls, and `--proxy URL` sets a proxy (the default is `VERSLINE_LLM_PROXY`). If GitHub rate-limits you, set `GITHUB_TOKEN`.

After the **first** install, open Obsidian, go to **Settings → Community plugins**, turn off Restricted mode if asked, and enable **Versobs**. After an update, reload Obsidian or disable and re-enable the plugin.

Inside Obsidian, the plugin can also update itself: **Settings → Versobs → Update plugin** runs the same installer for the current vault.

## How the plugin talks to Versline

For every job the plugin runs `versline bridge run <tool>`, a JSON interface described in [Library: Bridge protocol](library.md#bridge-protocol). Jobs run in separate processes, so several can run at once. A job can be cancelled, and an interrupted job resumes on the next run like on the command line. Caches live in Versline's cache folder (`~/.cache/versline/bridge`, or `%LOCALAPPDATA%\versline\bridge` on Windows), never in your vault.
