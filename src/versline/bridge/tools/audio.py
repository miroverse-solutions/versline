"""Questions about one recorded talk: its taqrir, or finding the passages the listener remembers."""
import re
from pathlib import Path
from typing import List, Optional

from versline.bridge.registry import F, Params, tool, tr
from versline.bridge.tools._common import MARKDOWN, MEDIA, force_field
from versline.services.audio_points import skipped_warnings

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


class AudioTaqrirParams(Params):
    input: str = F(..., en="Audio/video or transcript", fa="فایل صوتی/ویدیویی یا متن پیاده‌شده", widget="file",
                   accept=MEDIA + MARKDOWN,
                   help_en="A transcript note is used as is; audio is transcribed once and remembered.",
                   help_fa="یادداشت متن پیاده‌شده همان‌طور استفاده می‌شود؛ صوت یک بار پیاده و ذخیره می‌شود.")
    output: Optional[str] = F(None, en="Output", fa="خروجی", widget="output-file", output="{dir}/{stem} - تقریر.md")
    instruction: Optional[str] = F(None, en="Focus / guidance", fa="محور یا راهنمایی", widget="textarea",
                                   help_en="e.g. 'only the second half', 'focus on the arguments about…'.",
                                   help_fa="مثلاً «فقط نیمه‌ی دوم» یا «روی استدلال‌های مربوط به … تمرکز کن».")
    output_lang: Optional[str] = F(None, en="Language", fa="زبان", advanced=True)
    skip_blocked: bool = F(False, en="Skip blocked chunks", fa="رد شدن از تکه‌های مسدودشده", advanced=True)
    force: bool = force_field()


class AudioFindParams(Params):
    input: str = F(..., en="Audio/video", fa="فایل صوتی/ویدیویی", widget="file", accept=MEDIA)
    query: str = F(..., en="What to find", fa="چه چیزی پیدا شود", widget="textarea", min_length=2,
                   help_en="Describe it as you remember it, e.g. 'the narration from Imam Sadiq about patience'.",
                   help_fa="همان‌طور که یادتان هست توصیف کنید؛ مثلاً «روایتی که از امام صادق درباره‌ی صبر خواند».")
    output: Optional[str] = F(None, en="Output", fa="خروجی", widget="output-file", output="{dir}/{stem} - نکته‌ها.md",
                              help_en="New findings are added to this note.", help_fa="یافته‌های تازه به این یادداشت اضافه می‌شود.")
    clip: bool = F(True, en="Cut audio clips", fa="بریدن تکه‌ی صوتی",
                   help_en="Save each passage as a short audio file next to the note.",
                   help_fa="هر بخش پیداشده به‌صورت فایل صوتی کوتاه کنار یادداشت ذخیره شود.")
    refine: bool = F(True, en="Re-transcribe found passages", fa="پیاده‌سازی دوباره‌ی بخش‌های پیداشده",
                     help_en="Transcribe each passage again on its own for an exact text (narrations, Arabic).",
                     help_fa="هر بخش جداگانه دوباره پیاده شود تا متن دقیق‌تر باشد (روایت، متن عربی).")
    output_lang: Optional[str] = F(None, en="Language", fa="زبان", advanced=True)
    skip_blocked: bool = F(False, en="Skip blocked chunks", fa="رد شدن از تکه‌های مسدودشده", advanced=True)
    force: bool = F(False, en="Transcribe again", fa="پیاده‌سازی دوباره", advanced=True,
                    help_en="Ignore the saved transcript of this file.", help_fa="متن ذخیره‌شده‌ی این فایل نادیده گرفته شود.")


def _services(ctx):
    from versline.services.channel_archive.llm import TextLLM
    from versline.services.transcription import AudioTranscriber

    transcriber = AudioTranscriber()

    def factory(note: str):
        sub = AudioTranscriber(user_note=note)
        sub.tracker = transcriber.tracker
        return sub

    return transcriber, factory, TextLLM(transcriber.tracker)


def _progress(ctx):
    def report(message: str) -> None:
        ctx.check_cancel()
        ctx.progress(None, None, message)

    return report


def _report_cost(ctx, tracker) -> None:
    from versline.config import settings
    from versline.services.pricing import cost_summary

    ctx.cost(cost_summary(tracker, api_key=settings.llm.api_key))


def _default_output(source: Path, suffix: str) -> Path:
    return source.with_name(f"{source.stem} - {suffix}.md")


@tool("audio.taqrir", category="media", params=AudioTaqrirParams,
      title=tr("Taqrir of a talk", "تقریر سخنرانی"),
      description=tr("Write the whole talk (audio, video or a transcript) up as a structured, faithful exposition.",
                     "کل سخنرانی (صوت، ویدیو یا متن پیاده‌شده) را به‌صورت تقریری منظم و وفادار به گوینده می‌نویسد."),
      tags=["audio", "video", "taqrir"])
def audio_taqrir(p: AudioTaqrirParams, ctx):
    from versline.services import transcript_cache
    from versline.services.audio_points import write_taqrir

    source = Path(p.input).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"File not found: {source}")
    output = Path(p.output).expanduser() if p.output else _default_output(source, "تقریر")
    transcriber, _, llm = _services(ctx)
    progress = _progress(ctx)
    warnings: List[dict] = []
    if source.suffix.lower() in MARKDOWN:
        text = _FRONTMATTER.sub("", source.read_text(encoding="utf-8")).strip()
    else:
        _, transcript = transcript_cache.get_or_transcribe(
            source, transcriber, force=p.force, skip_blocked=p.skip_blocked, progress=progress)
        text = transcript.text
        warnings = skipped_warnings(source, output, transcript.skipped_ranges)
    if not text:
        raise ValueError(f"{source.name} has no text to write a taqrir of.")
    taqrir = write_taqrir(llm, text, p.instruction, p.output_lang or "", progress=progress)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(taqrir.strip() + "\n", encoding="utf-8")
    ctx.artifact(output)
    _report_cost(ctx, transcriber.tracker)
    return {"outputs": [str(output)], "warnings": warnings}


@tool("audio.find", category="media", params=AudioFindParams,
      title=tr("Find a passage in a talk", "پیدا کردن نکته در سخنرانی"),
      description=tr("Find where something you remember was said (a point, a quotation, a narration) and write it out "
                     "with its time and an audio clip.",
                     "جایی را که نکته، قول یا روایتی در آن گفته شده پیدا می‌کند و متنش را با زمان دقیق و تکه‌ی صوتی می‌آورد."),
      tags=["audio", "video", "search"])
def audio_find(p: AudioFindParams, ctx):
    from versline.services import transcript_cache
    from versline.services.audio_points import append_section, render_find_section, run_find
    from versline.bridge.tools._common import scratch_dir

    source = Path(p.input).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"File not found: {source}")
    output = Path(p.output).expanduser() if p.output else _default_output(source, "نکته‌ها")
    transcriber, factory, llm = _services(ctx)
    progress = _progress(ctx)
    _, transcript = transcript_cache.get_or_transcribe(
        source, transcriber, force=p.force, skip_blocked=p.skip_blocked, progress=progress)
    with scratch_dir("find-") as work:
        result = run_find(
            llm, transcript, p.query, audio=source if (p.clip or p.refine) else None,
            clips_dir=output.parent if p.clip else None, clip_prefix=output.stem, refine=p.refine,
            transcriber_factory=factory, work=work, output_lang=p.output_lang or "", progress=progress,
        )
    append_section(output, render_find_section(result), source.stem)
    ctx.artifact(output)
    for passage in result.passages:
        if passage.clip is not None:
            ctx.artifact(passage.clip)
    _report_cost(ctx, transcriber.tracker)
    return {
        "outputs": [str(output)],
        "found": len(result.passages),
        "warnings": skipped_warnings(source, output, transcript.skipped_ranges),
    }
