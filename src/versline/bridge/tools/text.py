"""Translation and summarization tools (files and plain text)."""
from pathlib import Path
from typing import List, Literal, Optional

from versline.bridge.adapter import run_command
from versline.bridge.registry import F, Params, tool, tr
from versline.bridge.tools._common import DOCUMENTS, MARKDOWN, as_paths, force_field, note_field, parent_dirs, scratch_dir

LANGUAGE_HELP = tr("Language name, e.g. Persian, English, Arabic, French.",
                   "نام زبان، مثلاً Persian، English، Arabic یا French.")

SummaryMode = Literal["outline", "detailed", "slides"]
MODE_CHOICES = {
    "outline": tr("Outline (headings only)", "فهرست تفصیلی (سرفصل‌ها)"),
    "detailed": tr("Detailed summary", "خلاصه‌ی تفصیلی"),
    "slides": tr("Slide outline", "طرح اسلاید"),
}


# ---------------------------------------------------------------- translate

class TranslateFileParams(Params):
    inputs: List[str] = F(..., en="Files", fa="فایل‌ها", widget="files", accept=MARKDOWN, min_length=1)
    output: Optional[str] = F(None, en="Output", fa="خروجی", widget="output-file", output="{dir}/{stem}_translated.md",
                              help_en="Base path; a .md and a plain .txt are written. A folder for several inputs.",
                              help_fa="مسیر پایه؛ یک ‎.md‎ و یک ‎.txt‎ ساخته می‌شود. برای چند ورودی یک پوشه.")
    target_lang: str = F("Persian", en="Target language", fa="زبان مقصد",
                         help_en=LANGUAGE_HELP["en"], help_fa=LANGUAGE_HELP["fa"])
    recursive: bool = F(False, en="Include sub-folders", fa="شامل زیرپوشه‌ها", advanced=True)
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("translate.file", category="text", params=TranslateFileParams,
      title=tr("Translate file", "ترجمه‌ی فایل"),
      description=tr("Translate Markdown/text files, chunk by chunk, keeping the formatting.",
                     "فایل‌های Markdown یا متنی را تکه‌به‌تکه و با حفظ قالب ترجمه می‌کند."))
def translate_file(p: TranslateFileParams, ctx):
    output = Path(p.output).expanduser() if p.output else None
    watch = [output.with_suffix(".md") if output and output.suffix else output] if output else parent_dirs(as_paths(p.inputs))
    produced = run_command(ctx, "versline.commands.translate", "translate_file", outputs=watch,
                           file_paths=p.inputs, output=output, target_lang=p.target_lang,
                           recursive=p.recursive, note=p.note, force=p.force)
    return {"outputs": [str(x) for x in produced]}


class TranslateTextParams(Params):
    text: str = F(..., en="Text", fa="متن", widget="textarea", min_length=1)
    target_lang: str = F("Persian", en="Target language", fa="زبان مقصد",
                         help_en=LANGUAGE_HELP["en"], help_fa=LANGUAGE_HELP["fa"])
    note: Optional[str] = note_field()


@tool("translate.text", category="text", params=TranslateTextParams, hidden=True,
      title=tr("Translate text", "ترجمه‌ی متن"),
      description=tr("Translate a piece of text and return it.", "یک متن را ترجمه می‌کند و برمی‌گرداند."))
def translate_text(p: TranslateTextParams, ctx):
    with scratch_dir("translate-") as folder:
        source = folder / "text.md"
        source.write_text(p.text, encoding="utf-8")
        out = folder / "result.md"
        run_command(ctx, "versline.commands.translate", "translate_file", outputs=[],
                    file_paths=[source], output=out, target_lang=p.target_lang, note=p.note, force=True)
        return {"text": out.read_text(encoding="utf-8")}


# ---------------------------------------------------------------- summarize

class SummarizeFileParams(Params):
    inputs: List[str] = F(..., en="Files", fa="فایل‌ها", widget="files", accept=DOCUMENTS, min_length=1,
                          help_en="Markdown, text, PDF, Word, PowerPoint...", help_fa="Markdown، متن، PDF، Word، PowerPoint و…")
    output: Optional[str] = F(None, en="Output", fa="خروجی", widget="output-file", output="{dir}/{stem}_summary_{mode}.md")
    mode: SummaryMode = F("detailed", en="Mode", fa="نوع خلاصه", choices=MODE_CHOICES)
    output_lang: str = F("auto", en="Summary language", fa="زبان خلاصه",
                         help_en="'auto' keeps the source language.", help_fa="‏auto یعنی همان زبان متن اصلی.")
    compression: Optional[int] = F(None, en="Length (% of original)", fa="طول (درصد از متن اصلی)", ge=1, le=100,
                                   help_en="Empty: the model decides.", help_fa="خالی: مدل خودش تصمیم می‌گیرد.")
    preserve_terms: bool = F(True, en="Keep original terms", fa="حفظ اصطلاحات اصلی",
                             help_en="Add the source-language term in parentheses when translating.",
                             help_fa="اصطلاح زبان اصلی داخل پرانتز آورده شود.", advanced=True)
    didactic: bool = F(False, en="Didactic restructuring", fa="بازچینی آموزشی",
                       help_en="Reorder and expand for teaching (two passes).",
                       help_fa="برای آموزش بازچینی و بسط داده شود (دو مرحله‌ای).", advanced=True)
    recursive: bool = F(False, en="Include sub-folders", fa="شامل زیرپوشه‌ها", advanced=True)
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("summarize.file", category="text", params=SummarizeFileParams,
      title=tr("Summarize file", "خلاصه‌سازی فایل"),
      description=tr("Summarize an article, book or lecture notes as an outline, a detailed summary or slides.",
                     "مقاله، کتاب یا جزوه را به‌صورت فهرست، خلاصه‌ی تفصیلی یا طرح اسلاید خلاصه می‌کند."))
def summarize_file(p: SummarizeFileParams, ctx):
    output = Path(p.output).expanduser() if p.output else None
    watch = [output] if output else parent_dirs(as_paths(p.inputs))
    produced = run_command(ctx, "versline.commands.summarize", "summarize_file", outputs=watch,
                           file_paths=p.inputs, output=output, mode=p.mode, output_lang=p.output_lang,
                           compression=p.compression, preserve_terms=p.preserve_terms, didactic=p.didactic,
                           recursive=p.recursive, note=p.note, force=p.force)
    return {"outputs": [str(x) for x in produced]}


class SummarizeTextParams(Params):
    text: str = F(..., en="Text", fa="متن", widget="textarea", min_length=1)
    mode: SummaryMode = F("detailed", en="Mode", fa="نوع خلاصه", choices=MODE_CHOICES)
    output_lang: str = F("auto", en="Summary language", fa="زبان خلاصه")
    compression: Optional[int] = F(None, en="Length (% of original)", fa="طول (درصد از متن اصلی)", ge=1, le=100)
    note: Optional[str] = note_field()


@tool("summarize.text", category="text", params=SummarizeTextParams, hidden=True,
      title=tr("Summarize text", "خلاصه‌سازی متن"),
      description=tr("Summarize a piece of text and return it.", "یک متن را خلاصه می‌کند و برمی‌گرداند."))
def summarize_text(p: SummarizeTextParams, ctx):
    with scratch_dir("summarize-") as folder:
        source = folder / "text.md"
        source.write_text(p.text, encoding="utf-8")
        out = folder / "result.md"
        run_command(ctx, "versline.commands.summarize", "summarize_file", outputs=[],
                    file_paths=[source], output=out, mode=p.mode, output_lang=p.output_lang,
                    compression=p.compression, note=p.note, force=True)
        return {"text": out.read_text(encoding="utf-8")}
