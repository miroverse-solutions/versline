"""Versline itself: environment info, settings (config.env), updates, and the Obsidian plugin installer."""
import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional

from versline.bridge.adapter import run_command
from versline.bridge.registry import F, Params, tool, tr

# Keys a client may write. Anything else in config.env is left alone.
WRITABLE_KEYS = {
    "VERSLINE_LLM_PROVIDER", "VERSLINE_LLM_API_KEY", "VERSLINE_LLM_MODEL", "VERSLINE_LLM_API_ENDPOINT",
    "VERSLINE_LLM_PROXY", "VERSLINE_TELEGRAM_PROXY", "VERSLINE_TRANSCRIPTION_TIMESTAMP_MODEL",
    "VERSLINE_TRANSCRIPTION_TIMESTAMP_API_KEY", "VERSLINE_TRANSCRIPTION_TIMESTAMP_PROVIDER",
    "VERSLINE_EXPORT_PAGE_FORMAT", "VERSLINE_EXPORT_MARGIN",
    "VERSLINE_TRANSCRIPTION_FALLBACK_MODEL", "VERSLINE_TRANSCRIPTION_FALLBACK_PROVIDER",
    "VERSLINE_TRANSCRIPTION_FALLBACK_API_KEY", "VERSLINE_TRANSCRIPTION_FALLBACK_API_ENDPOINT",
}
PROVIDER_KEYS = ("VERSLINE_LLM_PROVIDER", "VERSLINE_TRANSCRIPTION_FALLBACK_PROVIDER")


class NoParams(Params):
    pass


@tool("system.info", category="system", params=NoParams, needs_llm=False, hidden=True,
      title=tr("Versline info", "اطلاعات ورس‌لاین"),
      description=tr("Version, settings file and optional features.", "نسخه، فایل تنظیمات و قابلیت‌های اختیاری."))
def info(p: NoParams, ctx):
    from versline import __version__
    from versline.config import settings
    from versline.userconfig import user_env_path

    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": sys.platform,
        "executable": sys.executable,
        "config_path": str(user_env_path()),
        "workdir": os.getcwd(),
        "provider": settings.llm.provider,
        "model": settings.llm.model,
        "has_api_key": bool(settings.llm.api_key),
        "proxy": settings.llm.proxy,
        "features": {
            "export": importlib.util.find_spec("mdpersia") is not None,
            "node": shutil.which("node") is not None,
            "telegram_credentials": bool(settings.telegram.api_id and settings.telegram.api_hash),
        },
    }


@tool("config.get", category="system", params=NoParams, needs_llm=False, hidden=True,
      title=tr("Read settings", "خواندن تنظیمات"),
      description=tr("Saved settings with secrets masked, plus providers and suggested models.",
                     "تنظیمات ذخیره‌شده با کلیدهای پوشیده، همراه با فهرست سرویس‌ها و مدل‌های پیشنهادی."))
def config_get(p: NoParams, ctx):
    from versline.userconfig import user_env_path
    from versline.userenv import DEFAULT_MODELS, PROVIDERS, is_secret, mask, read_env

    values = read_env()
    return {
        "path": str(user_env_path()),
        "values": {k: mask(k, v) for k, v in values.items()},
        "secrets_set": sorted(k for k, v in values.items() if is_secret(k) and v),
        "providers": PROVIDERS,
        "default_models": DEFAULT_MODELS,
        "writable": sorted(WRITABLE_KEYS),
    }


class ConfigSetParams(Params):
    values: Dict[str, Optional[str]] = F(..., en="Values", fa="مقادیر",
                                         help_en="KEY: value; null or empty removes the key.",
                                         help_fa="کلید: مقدار؛ مقدار خالی کلید را حذف می‌کند.")


@tool("config.set", category="system", params=ConfigSetParams, needs_llm=False, hidden=True,
      title=tr("Save settings", "ذخیره‌ی تنظیمات"),
      description=tr("Write provider, model, API key and proxy to Versline's settings file.",
                     "سرویس، مدل، کلید API و پروکسی را در فایل تنظیمات ورس‌لاین ذخیره می‌کند."))
def config_set(p: ConfigSetParams, ctx):
    from versline.userenv import PROVIDERS, update_env

    bad = sorted(set(p.values) - WRITABLE_KEYS)
    if bad:
        raise ValueError(f"Not writable: {', '.join(bad)}")
    for key in PROVIDER_KEYS:
        provider = p.values.get(key)
        if provider and provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}; choose from {', '.join(PROVIDERS)}")
    update_env(dict(p.values))
    return config_get(NoParams(), ctx)


@tool("system.check_update", category="system", params=NoParams, needs_llm=False, hidden=True,
      title=tr("Check for Versline updates", "بررسی نسخه‌ی جدید ورس‌لاین"),
      description=tr("Compare the installed version with the latest release.", "نسخه‌ی نصب‌شده را با آخرین نسخه مقایسه می‌کند."))
def check_update(p: NoParams, ctx):
    from versline import __version__
    from versline.commands.setup import REPO
    from versline.config import settings
    from versline.services.releases import fetch_release, is_newer

    release = fetch_release(REPO, timeout=15, proxy=settings.llm.proxy or None)
    latest = (release["tag"] or "").lstrip("vV")
    return {"current": __version__, "latest": latest, "update_available": is_newer(latest, __version__),
            "url": release.get("url")}


@tool("system.update", category="system", params=NoParams, needs_llm=False, hidden=True,
      title=tr("Update Versline", "به‌روزرسانی ورس‌لاین"),
      description=tr("Install the latest Versline release.", "آخرین نسخه‌ی ورس‌لاین را نصب می‌کند."))
def update(p: NoParams, ctx):
    run_command(ctx, "versline.commands.setup", "update_command")
    return {"platform": sys.platform}


# ---------------------------------------------------------------- Obsidian plugin


class VaultParams(Params):
    vault: Optional[str] = F(None, en="Vault", fa="والت", widget="folder",
                             help_en="Empty: the most recently opened vault.", help_fa="خالی: آخرین والتی که باز شده است.")
    proxy: Optional[str] = F(None, en="Proxy", fa="پروکسی", advanced=True)


class InstallParams(VaultParams):
    version: Optional[str] = F(None, en="Version", fa="نسخه", help_en="Empty: the latest release.",
                               help_fa="خالی: آخرین نسخه.", advanced=True)
    force: bool = F(False, en="Reinstall", fa="نصب دوباره", advanced=True)


@tool("obsidian.vaults", category="obsidian", params=NoParams, needs_llm=False, hidden=True,
      title=tr("Obsidian vaults", "والت‌های Obsidian"),
      description=tr("Vaults known to Obsidian on this computer.", "والت‌هایی که Obsidian روی این رایانه می‌شناسد."))
def vaults(p: NoParams, ctx):
    from versline.services.obsidian_plugin import known_vaults

    return {"vaults": known_vaults()}


@tool("obsidian.status", category="obsidian", params=VaultParams, needs_llm=False, hidden=True,
      title=tr("Plugin status", "وضعیت افزونه"),
      description=tr("Installed and latest version of the Versobs plugin in a vault.",
                     "نسخه‌ی نصب‌شده و آخرین نسخه‌ی افزونه‌ی Versobs در یک والت."))
def plugin_status(p: VaultParams, ctx):
    from versline.services.obsidian_plugin import plugin_status as status

    return status(Path(p.vault) if p.vault else None, proxy=p.proxy)


@tool("obsidian.install", category="obsidian", params=InstallParams, needs_llm=False, hidden=True,
      title=tr("Install/update the plugin", "نصب/به‌روزرسانی افزونه"),
      description=tr("Download the latest Versobs release into the vault (settings are kept).",
                     "آخرین نسخه‌ی Versobs را در والت نصب می‌کند (تنظیمات حفظ می‌شوند)."))
def plugin_install(p: InstallParams, ctx):
    from versline.services.obsidian_plugin import install_plugin

    ctx.progress(None, None, "Downloading…")
    result = install_plugin(Path(p.vault) if p.vault else None, tag=p.version, proxy=p.proxy, force=p.force)
    return result.to_dict()
