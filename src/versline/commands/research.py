import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from versline.config import settings
from versline.core.prompts import resolve_text_input, resolve_user_note
from versline.services.document_processor import convert_to_markdown
from versline.services.pricing import print_cost_report
from versline.services.research_writing import ResearchWritingService, load_research_input


app = typer.Typer(
    help=(
        "Research section writing with a staged pipeline: "
        "generate outline first, then generate final full text from approved outline."
    )
)


def _read_material_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt", ".json", ".csv", ".yaml", ".yml"}:
        return file_path.read_text(encoding="utf-8")
    return convert_to_markdown(str(file_path))


def _collect_interviews(interviews_dir: Optional[Path], interview_files: List[Path]) -> List[Dict[str, str]]:
    collected: List[Path] = []
    if interviews_dir:
        extensions = {".md", ".markdown", ".txt", ".docx", ".pdf", ".csv", ".json"}
        for path in sorted(interviews_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in extensions:
                collected.append(path)
    collected.extend(interview_files)

    unique: List[Path] = []
    seen = set()
    for path in collected:
        marker = str(path.resolve())
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(path)

    interviews = []
    for path in unique:
        interviews.append({"name": path.name, "content": _read_material_file(path)})
    return interviews


def _collect_coded_segments(
    coded_segments_dir: Optional[Path],
    coded_segment_files: List[Path],
) -> List[Dict[str, str]]:
    collected: List[Path] = []
    if coded_segments_dir:
        extensions = {".md", ".markdown", ".txt", ".docx", ".pdf", ".csv", ".json", ".xlsx", ".xls"}
        for path in sorted(coded_segments_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in extensions:
                collected.append(path)
    collected.extend(coded_segment_files)

    unique: List[Path] = []
    seen = set()
    for path in collected:
        marker = str(path.resolve())
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(path)

    coded_segments = []
    for path in unique:
        coded_segments.append({"name": path.name, "content": _read_material_file(path)})
    return coded_segments


def _enrich_inputs(
    base_input: Dict[str, Any],
    demographics_file: Optional[Path],
    themes_table_file: Optional[Path],
    central_concepts_file: Optional[Path],
    coded_segments: List[Dict[str, str]],
    writing_guide_file: Optional[Path],
    sample_output_file: Optional[Path],
    interviews: List[Dict[str, str]],
) -> Dict[str, Any]:
    enriched = json.loads(json.dumps(base_input, ensure_ascii=False))
    materials = enriched.get("materials")
    if not isinstance(materials, dict):
        materials = {}

    if demographics_file:
        materials["demographics_table"] = _read_material_file(demographics_file)
    if themes_table_file:
        materials["themes_table"] = _read_material_file(themes_table_file)
    if central_concepts_file:
        materials["central_concepts"] = _read_material_file(central_concepts_file)
    if coded_segments:
        materials["coded_segments"] = coded_segments
    if writing_guide_file:
        materials["writing_guide"] = _read_material_file(writing_guide_file)
    if sample_output_file:
        materials["sample_output"] = _read_material_file(sample_output_file)
    if interviews:
        materials["interviews"] = interviews

    enriched["materials"] = materials
    return enriched


def _resolve_output_path(
    output: Optional[Path],
    input_json: Optional[Path],
    section: str,
    stage: str,
) -> Path:
    if output:
        base = output.with_suffix("") if output.suffix else output
        return base.with_suffix(".md")

    stem = input_json.stem if input_json else "research"
    return Path("output") / f"{stem}_{section}_{stage}.md"


@app.callback(invoke_without_command=True)
def write_research_section(
    ctx: typer.Context,
    input_json: Optional[Path] = typer.Option(
        None,
        "--input-json",
        "-i",
        help="Path to research input JSON containing study metadata and materials.",
        exists=True,
    ),
    stage: str = typer.Option(
        "outline",
        "--stage",
        "-s",
        help="Pipeline stage: outline or full",
    ),
    section: str = typer.Option(
        "findings",
        "--section",
        help="Research section to write (currently: findings)",
    ),
    method: str = typer.Option(
        "thematic-colaizzi",
        "--method",
        "-m",
        help="Research method profile (currently: thematic-colaizzi)",
    ),
    output_lang: str = typer.Option(
        "auto",
        "--output-lang",
        "-l",
        help="Output language. 'auto' keeps source language.",
    ),
    approved_outline_file: Optional[Path] = typer.Option(
        None,
        "--approved-outline-file",
        help="Path to the user-approved outline markdown (required for --stage full).",
        exists=True,
    ),
    approve_outline: bool = typer.Option(
        False,
        "--approve-outline",
        help="Explicit confirmation that the provided outline is user-approved.",
    ),
    demographics_file: Optional[Path] = typer.Option(
        None,
        "--demographics-file",
        help="Demographic table/material file (csv/xlsx/md/txt/docx/pdf).",
        exists=True,
    ),
    themes_table_file: Optional[Path] = typer.Option(
        None,
        "--themes-table-file",
        help="Themes/sub-themes table file (e.g., findings theme matrix in xlsx/csv/md/docx/pdf).",
        exists=True,
    ),
    central_concepts_file: Optional[Path] = typer.Option(
        None,
        "--central-concepts-file",
        help="Central concepts/themes material file.",
        exists=True,
    ),
    coded_segments_file: List[Path] = typer.Option(
        [],
        "--coded-segments-file",
        help="Coded segments/codes file (repeatable; e.g., MAXQDA analysis export).",
        exists=True,
    ),
    coded_segments_dir: Optional[Path] = typer.Option(
        None,
        "--coded-segments-dir",
        help="Directory containing coded segments/code files.",
        exists=True,
        file_okay=False,
    ),
    writing_guide_file: Optional[Path] = typer.Option(
        None,
        "--writing-guide-file",
        help=(
            "Structured writing instruction file (md/docx/txt recommended) "
            "that defines required chapter layout and wording constraints."
        ),
        exists=True,
    ),
    sample_output_file: Optional[Path] = typer.Option(
        None,
        "--sample-output-file",
        help=(
            "A sample chapter/output file (md/docx/txt recommended) whose style, "
            "formatting, and rhetorical flow should be emulated."
        ),
        exists=True,
    ),
    interviews_dir: Optional[Path] = typer.Option(
        None,
        "--interviews-dir",
        help="Directory containing interview files.",
        exists=True,
        file_okay=False,
    ),
    interview_file: List[Path] = typer.Option(
        [],
        "--interview-file",
        help="Single interview file (repeatable).",
        exists=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .md path",
    ),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model to use"),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="LLM provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)",
    ),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to note file (.md/.txt)"),
    revision_file: Optional[Path] = typer.Option(
        None,
        "--revision-file",
        help="Path to a .md/.txt revision brief used to re-run the chapter with corrections.",
        exists=True,
    ),
):
    if ctx.invoked_subcommand is not None:
        return

    if stage not in {"outline", "full"}:
        raise typer.BadParameter("stage must be 'outline' or 'full'")

    if stage == "full":
        if approved_outline_file is None:
            raise typer.BadParameter("--approved-outline-file is required for --stage full")
        if not approve_outline:
            raise typer.BadParameter("Pass --approve-outline to confirm user approval before full generation")

    if model:
        settings.llm.model = model
    if provider:
        settings.llm.provider = provider
    if api_key:
        settings.llm.api_key = api_key
    if api_endpoint:
        settings.llm.api_endpoint = api_endpoint
    if proxy:
        settings.llm.proxy = proxy

    try:
        base_input = load_research_input(str(input_json)) if input_json else {}
        interviews = _collect_interviews(interviews_dir=interviews_dir, interview_files=interview_file)
        coded_segments = _collect_coded_segments(
            coded_segments_dir=coded_segments_dir,
            coded_segment_files=coded_segments_file,
        )
        research_inputs = _enrich_inputs(
            base_input=base_input,
            demographics_file=demographics_file,
            themes_table_file=themes_table_file,
            central_concepts_file=central_concepts_file,
            coded_segments=coded_segments,
            writing_guide_file=writing_guide_file,
            sample_output_file=sample_output_file,
            interviews=interviews,
        )

        service = ResearchWritingService(
            section=section,
            method=method,
            user_note=resolve_user_note(note=note, note_file=str(note_file) if note_file else None),
            revision_note=resolve_text_input(
                text_file=str(revision_file) if revision_file else None,
                label="Revision",
                allowed_suffixes=(".md", ".txt"),
            ),
            output_lang=output_lang,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=False,
        ) as progress:
            task = progress.add_task("Preparing research writing...", total=100)
            progress.update(task, completed=20, description=f"Generating {stage} for {section}...")

            if stage == "outline":
                result = service.generate_outline(research_inputs=research_inputs)
            else:
                approved_outline = approved_outline_file.read_text(encoding="utf-8")
                result = service.generate_full_text(
                    research_inputs=research_inputs,
                    approved_outline=approved_outline,
                )

            progress.update(task, completed=100, description=f"{stage.title()} generated")

        out_path = _resolve_output_path(output=output, input_json=input_json, section=section, stage=stage)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")

        logger.success(f"Saved {stage} output to: {out_path}")
        print_cost_report(service.tracker, api_key=settings.llm.api_key)

    except Exception as exc:
        logger.error(f"Research writing failed: {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
