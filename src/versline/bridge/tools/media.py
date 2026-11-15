"""Transcription tools."""
from pathlib import Path
from typing import List, Optional

from versline.bridge.adapter import run_command
from versline.bridge.registry import F, Params, tool, tr
from versline.bridge.tools._common import MEDIA, force_field, note_field


class TranscribeParams(Params):
    inputs: List[str] = F(..., en="Audio/video files or links", fa="فایل‌ها یا لینک‌های صوت/ویدیو",
                          widget="files", accept=MEDIA, min_length=1,
                          help_en="Local files, folders or http(s) links.", help_fa="فایل، پوشه یا لینک http(s).")
    output: Optional[str] = F(None, en="Output", fa="خروجی", widget="output-file", output="{dir}/{stem}.md",
                              help_en="A .md file for one input, a folder for several.",
                              help_fa="برای یک ورودی فایل ‎.md‎ و برای چند ورودی یک پوشه.")
    timestamped: bool = F(False, en="With timestamps", fa="همراه با زمان‌بندی",
                          help_en="Also produce time-aligned segments (JSON + .md).",
                          help_fa="بخش‌های زمان‌دار هم ساخته شود (JSON و ‎.md‎).")
    json_output: bool = F(False, en="Structured JSON", fa="خروجی JSON ساختاریافته", advanced=True)
    chunk_size: int = F(900, en="Chunk length (s)", fa="طول هر تکه (ثانیه)", ge=60, advanced=True)
    overlap: int = F(180, en="Chunk overlap (s)", fa="هم‌پوشانی تکه‌ها (ثانیه)", ge=0, advanced=True)
    compress: bool = F(False, en="Compress audio first", fa="فشرده‌سازی صوت پیش از ارسال",
                       help_en="Avoids provider payload limits for long files.",
                       help_fa="برای فایل‌های طولانی از محدودیت حجم سرویس جلوگیری می‌کند.", advanced=True)
    skip_blocked: bool = F(False, en="Skip blocked chunks", fa="رد شدن از تکه‌های مسدودشده", advanced=True)
    recursive: bool = F(False, en="Include sub-folders", fa="شامل زیرپوشه‌ها", advanced=True)
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("transcribe", category="media", params=TranscribeParams,
      title=tr("Transcribe audio/video", "پیاده‌سازی صوت/ویدیو"),
      description=tr("Convert speech in audio or video files (or links) to text.",
                     "گفتار فایل‌ها یا لینک‌های صوتی و ویدیویی را به متن تبدیل می‌کند."),
      tags=["audio", "video"])
def transcribe(p: TranscribeParams, ctx):
    output = Path(p.output).expanduser() if p.output else None
    watch = [output] if output else [Path("output")]
    produced = run_command(
        ctx, "versline.commands.transcribe", "transcribe_file", outputs=watch,
        file_paths=p.inputs, output=output, timestamped=p.timestamped, json_output=p.json_output,
        chunk_size=p.chunk_size, overlap=p.overlap, compress=p.compress, skip_blocked=p.skip_blocked,
        recursive=p.recursive, note=p.note, force=p.force,
    )
    return {"outputs": [str(x) for x in produced]}
