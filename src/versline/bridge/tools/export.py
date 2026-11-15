"""Word/PDF export."""
from pathlib import Path
from typing import List, Literal, Optional

from versline.bridge.adapter import run_command
from versline.bridge.registry import F, Params, tool, tr
from versline.bridge.tools._common import as_paths, force_field, parent_dirs


class ExportParams(Params):
    inputs: List[str] = F(..., en="Notes or folders", fa="یادداشت‌ها یا پوشه‌ها", widget="files", accept=[".md", ".markdown"], min_length=1)
    to: Literal["docx", "pdf", "docx,pdf"] = F("docx,pdf", en="Formats", fa="قالب‌ها",
                                               choices={"docx": tr("Word", "Word"), "pdf": tr("PDF", "PDF"),
                                                        "docx,pdf": tr("Word + PDF", "Word و PDF")})
    output: Optional[str] = F(None, en="Output folder", fa="پوشه‌ی خروجی", widget="output-folder",
                              help_en="Empty: next to each note.", help_fa="خالی: کنار هر یادداشت.")
    front_matter: bool = F(True, en="Metadata table", fa="جدول مشخصات",
                           help_en="Show the note's properties as a table under the title.",
                           help_fa="ویژگی‌های یادداشت به‌صورت جدول زیر عنوان نمایش داده شود.")
    page_format: Optional[str] = F(None, en="Page size", fa="اندازه‌ی صفحه", help_en="A4, Letter, ...", advanced=True)
    margin: Optional[str] = F(None, en="Margin", fa="حاشیه", help_en="e.g. 15mm", advanced=True)
    landscape: bool = F(False, en="Landscape", fa="افقی", advanced=True)
    font_size: Optional[int] = F(None, en="Font size (pt, Word)", fa="اندازه‌ی قلم (Word)", ge=6, le=40, advanced=True)
    recursive: bool = F(False, en="Include sub-folders", fa="شامل زیرپوشه‌ها", advanced=True)
    force: bool = force_field()


@tool("export", category="export", params=ExportParams, needs_llm=False,
      title=tr("Export to Word/PDF", "خروجی Word/PDF"),
      description=tr("Convert notes to .docx and .pdf (Persian/RTL aware; embeds and wikilinks handled).",
                     "یادداشت‌ها را به ‎.docx‎ و ‎.pdf‎ تبدیل می‌کند (با پشتیبانی فارسی و راست‌به‌چپ و لینک‌های Obsidian)."))
def export(p: ExportParams, ctx):
    output = Path(p.output).expanduser() if p.output else None
    watch = [output] if output else parent_dirs(as_paths(p.inputs))
    produced = run_command(ctx, "versline.commands.export", "export_command", outputs=watch,
                           inputs=p.inputs, to=p.to, output=output, front_matter=p.front_matter,
                           page_format=p.page_format, margin=p.margin, landscape=p.landscape,
                           font_size=p.font_size, recursive=p.recursive, force=p.force)
    produced = [x for x in produced if x.suffix.lower() in (".docx", ".pdf")]
    return {"outputs": [str(x) for x in produced]}


class InstallBrowserParams(Params):
    pass


@tool("export.install_browser", category="export", params=InstallBrowserParams, needs_llm=False, hidden=True,
      title=tr("Install PDF browser", "نصب مرورگر PDF"),
      description=tr("Download the Chromium browser needed for PDF export.", "مرورگر Chromium لازم برای خروجی PDF را دانلود می‌کند."))
def install_browser(p: InstallBrowserParams, ctx):
    run_command(ctx, "versline.commands.export", "export_command", install_browser=True)
    return {}
