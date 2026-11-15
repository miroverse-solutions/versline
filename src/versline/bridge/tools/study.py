"""Study and research tools: questions/flashcards, qualitative coding, research writing, slides."""
import json
from pathlib import Path
from typing import List, Literal, Optional

from versline.bridge.adapter import run_command
from versline.bridge.registry import F, Params, tool, tr
from versline.bridge.tools._common import DOCUMENTS, MARKDOWN, force_field, note_field, scratch_dir

# ---------------------------------------------------------------- qude (questions / flashcards)


class QudeParams(Params):
    inputs: List[str] = F(..., en="Sources", fa="منابع", widget="files", accept=DOCUMENTS, min_length=1,
                          help_en="Files or folders (Markdown, PDF, Word, PowerPoint...).",
                          help_fa="فایل یا پوشه (Markdown، PDF، Word، PowerPoint و…).")
    output_dir: str = F(..., en="Output folder", fa="پوشه‌ی خروجی", widget="output-folder", output="{dir}/{stem}_questions")
    question_type: Literal["mcq", "open"] = F("mcq", en="Question type", fa="نوع سؤال",
                                               choices={"mcq": tr("Multiple choice", "چهارگزینه‌ای"),
                                                        "open": tr("Descriptive (flashcard)", "تشریحی (فلش‌کارت)")})
    language: str = F("fa", en="Language code", fa="کد زبان", help_en="e.g. fa, en", help_fa="مثلاً fa یا en")
    count: Optional[int] = F(None, en="Questions per chunk", fa="تعداد سؤال در هر بخش", ge=1,
                             help_en="Empty: as many as possible.", help_fa="خالی: هر چند تا که ممکن باشد.")
    formats: str = F("all", en="Formats", fa="قالب‌ها", help_en="csv, anki, html or all (comma-separated).",
                     help_fa="csv، anki، html یا all (با ویرگول جدا شوند).")
    answer_length: Optional[str] = F(None, en="Answer length", fa="طول پاسخ",
                                     help_en="For descriptive: a word count, short, medium, long or mixed.",
                                     help_fa="برای تشریحی: تعداد کلمه، short، medium، long یا mixed.", advanced=True)
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("qude", category="study", params=QudeParams,
      title=tr("Questions & flashcards", "سؤال و فلش‌کارت"),
      description=tr("Generate multiple-choice or descriptive questions and export them to CSV, Anki and HTML.",
                     "سؤال چهارگزینه‌ای یا تشریحی می‌سازد و به CSV، Anki و HTML خروجی می‌دهد."),
      tags=["anki", "flashcards"])
def qude(p: QudeParams, ctx):
    out = Path(p.output_dir).expanduser()
    produced = run_command(ctx, "versline.commands.qude", "main", outputs=[out],
                           input_paths=p.inputs, output_dir=out, question_type=p.question_type, language=p.language,
                           count=p.count, formats=p.formats, answer_length=p.answer_length, note=p.note, force=p.force)
    return {"outputs": [str(x) for x in produced], "output_dir": str(out)}


# ---------------------------------------------------------------- qualcode

Method = Literal["thematic", "grounded", "content", "framework", "colaizzi"]
METHOD_CHOICES = {
    "thematic": tr("Thematic analysis", "تحلیل مضمون"),
    "grounded": tr("Grounded theory", "نظریه‌ی داده‌بنیاد"),
    "content": tr("Content analysis", "تحلیل محتوا"),
    "framework": tr("Framework analysis", "تحلیل چارچوبی"),
    "colaizzi": tr("Colaizzi", "کلایزی"),
}


class QualcodeParams(Params):
    inputs: List[str] = F(..., en="Interviews / texts", fa="مصاحبه‌ها / متن‌ها", widget="files", accept=MARKDOWN, min_length=1)
    output_dir: str = F(..., en="Output folder", fa="پوشه‌ی خروجی", widget="output-folder", output="{dir}/{stem}_coding")
    methods: List[Method] = F(["thematic"], en="Methods", fa="روش‌ها", widget="tags", choices=METHOD_CHOICES, min_length=1)
    formats: List[Literal["json", "markdown", "csv", "segments-csv", "detailed-csv"]] = F(
        ["json", "markdown"], en="Formats", fa="قالب‌ها", widget="tags")
    codes: List[str] = F([], en="Seed codes", fa="کدهای اولیه", widget="tags", advanced=True)
    codebook: Optional[str] = F(None, en="Codebook file", fa="فایل کدنامه", widget="file",
                                accept=[".txt", ".md", ".csv", ".json"], advanced=True)
    central_concepts: Optional[str] = F(None, en="Central concepts file", fa="فایل مفاهیم محوری", widget="file", advanced=True)
    code_mode: Literal["guided", "strict"] = F("guided", en="Code mode", fa="حالت کدگذاری", advanced=True,
                                               choices={"guided": tr("Guided", "هدایت‌شده"), "strict": tr("Strict", "سخت‌گیرانه")})
    analysis_language: Literal["auto", "fa", "en"] = F("auto", en="Analysis language", fa="زبان تحلیل")
    citation: bool = F(False, en="Include evidence quotes", fa="همراه با نقل‌قول شاهد")
    words_per_batch: int = F(1200, en="Words per batch", fa="تعداد کلمه در هر دسته", ge=200, advanced=True)
    excel: bool = F(True, en="Also write Excel", fa="خروجی Excel هم ساخته شود", advanced=True)
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("qualcode", category="study", params=QualcodeParams,
      title=tr("Qualitative coding", "کدگذاری کیفی"),
      description=tr("Code interviews with thematic, grounded, content, framework or Colaizzi analysis.",
                     "مصاحبه‌ها را با روش تحلیل مضمون، داده‌بنیاد، محتوا، چارچوبی یا کلایزی کدگذاری می‌کند."))
def qualcode(p: QualcodeParams, ctx):
    out = Path(p.output_dir).expanduser()
    produced = run_command(ctx, "versline.commands.qualcode", "qualcode_file", outputs=[out],
                           input_paths=p.inputs, output_dir=out, methods=list(p.methods), formats=list(p.formats),
                           codes=list(p.codes), codebook=p.codebook, central_concepts=p.central_concepts,
                           code_mode=p.code_mode, analysis_language=p.analysis_language, citation=p.citation,
                           words_per_batch=p.words_per_batch, excel=p.excel, note=p.note, force=p.force)
    return {"outputs": [str(x) for x in produced], "output_dir": str(out)}


# ---------------------------------------------------------------- research


class ResearchCommon(Params):
    input_json: Optional[str] = F(None, en="Study JSON", fa="فایل JSON پژوهش", widget="file", accept=[".json"], advanced=True,
                                  help_en="Optional; the fields below are merged into it.",
                                  help_fa="اختیاری؛ فیلدهای زیر با آن ادغام می‌شوند.")
    title: Optional[str] = F(None, en="Study title", fa="عنوان پژوهش")
    domain: Optional[str] = F(None, en="Field", fa="رشته")
    research_questions: List[str] = F([], en="Research questions", fa="سؤال‌های پژوهش", widget="tags")
    output_lang: str = F("auto", en="Language", fa="زبان")
    demographics_file: Optional[str] = F(None, en="Demographics table", fa="جدول جمعیت‌شناختی", widget="file")
    themes_table_file: Optional[str] = F(None, en="Themes table", fa="جدول مضامین", widget="file")
    central_concepts_file: Optional[str] = F(None, en="Central concepts", fa="مفاهیم محوری", widget="file")
    coded_segments_dir: Optional[str] = F(None, en="Coded segments folder", fa="پوشه‌ی بخش‌های کدگذاری‌شده", widget="folder")
    interviews_dir: Optional[str] = F(None, en="Interviews folder", fa="پوشه‌ی مصاحبه‌ها", widget="folder")
    writing_guide_file: Optional[str] = F(None, en="Writing guide", fa="راهنمای نگارش", widget="file", advanced=True)
    sample_output_file: Optional[str] = F(None, en="Style sample", fa="نمونه‌ی سبک", widget="file", advanced=True)
    revision_file: Optional[str] = F(None, en="Revision brief", fa="یادداشت اصلاحات", widget="file", accept=[".md", ".txt"], advanced=True)
    note: Optional[str] = note_field()


class ResearchOutlineParams(ResearchCommon):
    output: str = F(..., en="Outline note", fa="یادداشت طرح", widget="output-file", output="{dir}/findings_outline.md")


class ResearchFullParams(ResearchCommon):
    approved_outline_file: str = F(..., en="Approved outline", fa="طرح تأییدشده", widget="file", accept=[".md"])
    approve_outline: bool = F(False, en="I approve this outline", fa="این طرح را تأیید می‌کنم",
                              help_en="Required: full text is only written from an outline you reviewed.",
                              help_fa="الزامی: متن کامل فقط از طرحی نوشته می‌شود که بازبینی کرده‌اید.")
    output: str = F(..., en="Output note", fa="یادداشت خروجی", widget="output-file", output="{dir}/findings_full.md")


def _study_json(p: ResearchCommon, folder: Path) -> Optional[Path]:
    if not (p.title or p.domain or p.research_questions):
        return Path(p.input_json).expanduser() if p.input_json else None
    data = json.loads(Path(p.input_json).expanduser().read_text(encoding="utf-8")) if p.input_json else {}
    study = data.setdefault("study", {})
    if p.title:
        study["title"] = p.title
    if p.domain:
        study["domain"] = p.domain
    if p.research_questions:
        study["research_questions"] = list(p.research_questions)
    study.setdefault("method", "thematic-colaizzi")
    path = folder / "study.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _research(p: ResearchCommon, ctx, stage: str, **extra):
    out = Path(p.output).expanduser()  # type: ignore[attr-defined]
    with scratch_dir("research-") as folder:
        produced = run_command(
            ctx, "versline.commands.research", "write_research_section", outputs=[out],
            input_json=_study_json(p, folder), stage=stage, output_lang=p.output_lang, output=out,
            demographics_file=p.demographics_file, themes_table_file=p.themes_table_file,
            central_concepts_file=p.central_concepts_file, coded_segments_dir=p.coded_segments_dir,
            interviews_dir=p.interviews_dir, writing_guide_file=p.writing_guide_file,
            sample_output_file=p.sample_output_file, revision_file=p.revision_file, note=p.note, **extra,
        )
    return {"outputs": [str(x) for x in produced]}


@tool("research.outline", category="research", params=ResearchOutlineParams,
      title=tr("Research findings: outline", "فصل یافته‌ها: طرح"),
      description=tr("Step 1: draft the outline of the findings chapter for you to review and edit.",
                     "مرحله‌ی ۱: طرح فصل یافته‌ها را برای بازبینی و ویرایش شما می‌نویسد."))
def research_outline(p: ResearchOutlineParams, ctx):
    return _research(p, ctx, "outline")


@tool("research.full", category="research", params=ResearchFullParams,
      title=tr("Research findings: full text", "فصل یافته‌ها: متن کامل"),
      description=tr("Step 2: write the full chapter from your approved outline.",
                     "مرحله‌ی ۲: متن کامل فصل را از طرح تأییدشده‌ی شما می‌نویسد."))
def research_full(p: ResearchFullParams, ctx):
    if not p.approve_outline:
        raise ValueError("Approve the outline first (approve_outline = true).")
    return _research(p, ctx, "full", approved_outline_file=p.approved_outline_file, approve_outline=True)


# ---------------------------------------------------------------- slides


class SlidesParams(Params):
    inputs: List[str] = F(..., en="Markdown notes", fa="یادداشت‌های Markdown", widget="files", accept=MARKDOWN, min_length=1)
    output_dir: str = F(..., en="Output folder", fa="پوشه‌ی خروجی", widget="output-folder", output="{dir}/{stem}_slides")
    engine: Literal["html", "revealjs", "impress"] = F("revealjs", en="Deck type", fa="نوع اسلاید",
                                                       choices={"html": tr("HTML/TypeScript", "HTML/TypeScript"),
                                                                "revealjs": tr("Reveal.js", "Reveal.js"),
                                                                "impress": tr("Impress.js (3D)", "Impress.js (سه‌بعدی)")})
    slide_size: Literal["small", "medium", "large"] = F("medium", en="Slide size", fa="اندازه‌ی اسلاید")
    font_family: str = F("Vazirmatn", en="Font", fa="قلم", advanced=True)
    include_all_content: bool = F(False, en="Keep all content", fa="حفظ همه‌ی محتوا", advanced=True)
    verbatim_text: bool = F(False, en="Use exact source text", fa="استفاده از متن دقیق منبع", advanced=True)
    no_scroll: bool = F(True, en="Fit without scrolling", fa="بدون نیاز به اسکرول", advanced=True)
    build: bool = F(False, en="Build with Vite (needs Node.js)", fa="ساخت با Vite (نیازمند Node.js)", advanced=True)
    single_file: bool = F(False, en="Single HTML file", fa="یک فایل HTML", advanced=True)
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("slides", category="study", params=SlidesParams,
      title=tr("Slides from a note", "اسلاید از یادداشت"),
      description=tr("Turn a Markdown note into an HTML slide deck (Reveal.js, Impress.js or HTML/TS).",
                     "یک یادداشت Markdown را به اسلاید HTML تبدیل می‌کند (Reveal.js، Impress.js یا HTML/TS)."))
def slides(p: SlidesParams, ctx):
    out = Path(p.output_dir).expanduser()
    produced = run_command(ctx, "versline.commands.slides", "generate_slides", outputs=[out],
                           input_paths=p.inputs, output_dir=out, use_revealjs=p.engine == "revealjs",
                           use_impress=p.engine == "impress", slide_size=p.slide_size, font_family=p.font_family,
                           include_all_content=p.include_all_content, verbatim_text=p.verbatim_text,
                           no_scroll=p.no_scroll, build=p.build, single_file=p.single_file,
                           note=p.note, force=p.force)
    decks = sorted({str(x) for x in produced if x.name == "index.html"})
    return {"outputs": [str(x) for x in produced], "decks": decks, "output_dir": str(out)}
