"""Read-only archive reports (catalogue, statistics, duplicates). `organize apply` is deliberately not exposed."""
import hashlib
import shutil
from pathlib import Path
from typing import List, Optional

from versline.bridge.adapter import run_command
from versline.bridge.registry import F, Params, tool, tr


class ReportParams(Params):
    sources: List[str] = F(..., en="Folders to analyse", fa="پوشه‌های مورد بررسی", widget="folder", min_length=1,
                           help_en="Never modified.", help_fa="هیچ تغییری در آن‌ها داده نمی‌شود.")
    copy_to: Optional[str] = F(None, en="Copy reports to", fa="کپی گزارش‌ها در", widget="output-folder",
                               help_en="A vault folder for the Markdown reports.", help_fa="پوشه‌ای در والت برای گزارش‌های Markdown.")
    duplicates: bool = F(True, en="Find duplicates", fa="یافتن تکراری‌ها")
    min_size: str = F("1", en="Ignore files smaller than", fa="نادیده‌گرفتن فایل‌های کوچک‌تر از",
                      help_en="e.g. 1, 100KB, 1MB", advanced=True)
    workspace: Optional[str] = F(None, en="Catalog folder", fa="پوشه‌ی کاتالوگ", widget="folder", advanced=True,
                                 help_en="Where the catalog database lives (default: Versline's cache).",
                                 help_fa="محل پایگاه‌داده‌ی کاتالوگ (پیش‌فرض: کش ورس‌لاین).")


def _default_workspace(sources: List[Path]) -> Path:
    key = hashlib.sha1("|".join(str(s.resolve()) for s in sources).encode("utf-8")).hexdigest()[:10]
    return (Path("organize") / f"{sources[0].name or 'root'}-{key}").resolve()


@tool("organize.report", category="organize", params=ReportParams, needs_llm=False,
      title=tr("Folder statistics & duplicates", "آمار پوشه و فایل‌های تکراری"),
      description=tr("Catalogue folders and report sizes, kinds and duplicate files (read-only, no AI).",
                     "پوشه‌ها را فهرست‌برداری و حجم، نوع و فایل‌های تکراری را گزارش می‌کند (فقط خواندنی، بدون هوش مصنوعی)."))
def report(p: ReportParams, ctx):
    sources = [Path(s).expanduser().resolve() for s in p.sources]
    workspace = Path(p.workspace).expanduser().resolve() if p.workspace else _default_workspace(sources)
    reports_dir = workspace / "reports"
    workspace.mkdir(parents=True, exist_ok=True)
    ctx.progress(None, None, "Scanning…")
    run_command(ctx, "versline.commands.organize", "scan", sources=sources, workspace=workspace)
    if p.duplicates:
        ctx.progress(None, None, "Finding duplicates…")
        run_command(ctx, "versline.commands.organize", "dupes", workspace=workspace, min_size=p.min_size)
    reports = sorted(reports_dir.glob("*.md")) if reports_dir.is_dir() else []
    copied: List[Path] = []
    if p.copy_to:
        target = Path(p.copy_to).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        for item in reports:
            dest = target / item.name
            shutil.copy2(item, dest)
            copied.append(dest)
    ctx.artifacts_from(copied or reports)
    return {"workspace": str(workspace), "reports": [str(r) for r in reports], "outputs": [str(c) for c in copied or reports]}
