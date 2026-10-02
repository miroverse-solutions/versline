import typer
from versline.config import settings, parse_extra_body

EXTRA_BODY_HELP = (
    'JSON object merged into every OpenAI-compatible request body, '
    'e.g. \'{"reasoning": {"max_tokens": 1500}}\''
)


def apply_extra_body_option(raw: str) -> None:
    try:
        settings.llm.extra_body = parse_extra_body(raw)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--extra-body")
