from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.progress import Progress, SpinnerColumn, TextColumn

from versline.config import settings
from versline.services.pricing import print_cost_report
from versline.services.slides import MarkdownSlideDeckGenerator
from versline.core.prompts import resolve_user_note

app = typer.Typer(help="Generate immersive HTML/CSS/TypeScript slide decks from Markdown.")


@app.callback(invoke_without_command=True)
def generate_slides(
    ctx: typer.Context,
    input_path: Optional[Path] = typer.Argument(None, help="Path to markdown input file", exists=True),
    output_dir: Path = typer.Option("output", "--output", "-o", help="Output directory"),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file", help="Custom prompt markdown file"),
    font_file: Optional[Path] = typer.Option(None, "--font-file", help="Local font file path (.ttf, .otf, .woff, .woff2)"),
    font_family: str = typer.Option("Vazirmatn", "--font-family", help="Font family name used in generated CSS"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model (overrides config)"),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="LLM provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)",
    ),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="LLM API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="HTTP/HTTPS proxy URL"),
    build: bool = typer.Option(False, "--build", help="Build generated deck with Vite"),
    single_file: bool = typer.Option(
        False,
        "--single-file",
        help="When building, enable vite-plugin-singlefile for one-file dist output",
    ),
    install_deps: bool = typer.Option(
        True,
        "--install-deps/--no-install-deps",
        help="Install npm dependencies before Vite build",
    ),
    include_all_content: bool = typer.Option(
        False,
        "--include-all-content/--no-include-all-content",
        help="Instruct the LLM to include ALL content from the input file without omitting anything.",
    ),
    verbatim_text: bool = typer.Option(
        False,
        "--verbatim-text/--no-verbatim-text",
        help="Instruct the LLM to use only exact verbatim text from the input file; no rephrasing.",
    ),
    no_scroll: bool = typer.Option(
        True,
        "--no-scroll/--allow-scroll",
        help="Design slides so all content fits without scrolling (default: on).",
    ),
    uniform_size: bool = typer.Option(
        True,
        "--uniform-size/--no-uniform-size",
        help="Make all slides the same size (default: on).",
    ),
    slide_size: str = typer.Option(
        "medium",
        "--slide-size",
        help="Slide size preset: small (720×480), medium (960×640), large (1280×800).",
    ),
    chunk_size: int = typer.Option(
        0,
        "--chunk-size",
        help=(
            "Split the markdown input into chunks of approximately this many characters "
            "and generate slides incrementally. Style is set from the first chunk and "
            "only slides are added for subsequent chunks. "
            "Set to 0 (default) to disable chunking and process the whole file at once."
        ),
    ),
    use_impress: bool = typer.Option(
        False,
        "--impress/--no-impress",
        help=(
            "Generate slides using Impress.js for cinematic 3D spatial navigation "
            "with zoom, rotation, and depth transitions. "
            "Produces a standalone HTML deck; impress.js is bundled automatically."
        ),
    ),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with an additional instruction"),
):
    """Generate a premium slide deck from markdown using LLM-guided code generation."""
    if ctx.invoked_subcommand is not None:
        return

    if input_path is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    if single_file and not build:
        logger.warning("--single-file has no effect without --build. Enabling --build automatically.")
        build = True

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

    generator = MarkdownSlideDeckGenerator(
        provider=settings.llm.provider,
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        api_endpoint=settings.llm.api_endpoint,
        proxy=settings.llm.proxy,
        prompt_path=str(prompt_file) if prompt_file else None,
        font_path=str(font_file) if font_file else None,
        font_family=font_family,
        include_all_content=include_all_content,
        verbatim_text=verbatim_text,
        no_scroll=no_scroll,
        uniform_size=uniform_size,
        slide_size=slide_size,
        use_impress=use_impress,
        user_note=resolve_user_note(note=note, note_file=str(note_file) if note_file else None),
    )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=False,
        ) as progress:
            task = progress.add_task("Calling LLM…", total=None)

            def on_progress(message: str) -> None:
                progress.update(task, description=message)

            result = generator.generate_from_markdown(
                input_path=str(input_path),
                output_dir=str(output_dir),
                build=build,
                single_file=single_file,
                install_deps=install_deps,
                chunk_size=chunk_size,
                progress_callback=on_progress,
            )
            progress.update(task, description="Slide deck generated ✓")

        logger.success(f"Deck directory: {result['deck_dir']}")
        logger.success(f"HTML: {result['index_html']}")
        logger.success(f"CSS: {result['style_css']}")
        logger.success(f"TypeScript: {result['main_ts']}")
        logger.success(f"Spatial mapping: {result['spatial_mapping']}")
        logger.success(f"Font file: {result['font_file']}")

        if result.get("impress_js"):
            logger.success(f"Impress.js: {result['impress_js']}")

        if result.get("dist_dir"):
            logger.success(f"Vite build output: {result['dist_dir']}")

        print_cost_report(generator.tracker, api_key=settings.llm.api_key)

    except Exception as error:
        logger.error(f"Slide generation failed: {error}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
