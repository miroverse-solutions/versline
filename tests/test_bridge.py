"""Bridge protocol, command adapter, manifest and an end-to-end tool run (LLM calls stubbed)."""
import io
import json
import sys
import types
from pathlib import Path
from typing import List, Optional

import pytest
import typer
from loguru import logger

from versline.bridge import PROTOCOL_VERSION
from versline.bridge.adapter import BridgeProgress, call_command, interactive, run_command
from versline.bridge.protocol import Cancelled, Emitter, JobContext, LogStream
from versline.bridge.registry import all_tools
from versline.bridge.runner import manifest, run


def events(buffer: io.StringIO) -> List[dict]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def restore_logger():
    yield
    logger.remove()
    logger.add(sys.stderr, level="INFO")


@pytest.fixture
def ctx():
    out = io.StringIO()
    return JobContext(Emitter(out), None), out


# ---------------------------------------------------------------- protocol


def test_log_stream_turns_lines_into_log_events():
    out = io.StringIO()
    stream = LogStream(Emitter(out))
    stream.write("[green]hello[/green]\npartial")
    stream.write(" line\n\n")
    assert [e["message"] for e in events(out)] == ["hello", "partial line"]
    assert not stream.isatty() and stream.encoding == "utf-8"


def test_ask_reads_the_matching_answer_from_stdin():
    out = io.StringIO()
    stdin = io.StringIO('{"type": "answer", "id": "p9", "value": "nope"}\n{"type": "answer", "id": "p1", "value": "42"}\n')
    context = JobContext(Emitter(out), stdin)
    assert context.ask("Code?", kind="code") == "42"
    prompt = events(out)[0]
    assert prompt == {"type": "prompt", "id": "p1", "message": "Code?", "secret": False, "kind": "code",
                      "default": None, "choices": None}


def test_ask_cancels_when_declined_or_stdin_closed():
    context = JobContext(Emitter(io.StringIO()), io.StringIO('{"type": "answer", "id": "p1", "value": null}\n'))
    with pytest.raises(Cancelled):
        context.ask("Phone?")
    with pytest.raises(Cancelled):
        JobContext(Emitter(io.StringIO()), None).ask("Phone?")


def test_bridge_progress_reports_updates(ctx):
    context, out = ctx
    BridgeProgress.ctx = context
    try:
        with BridgeProgress("columns", transient=True) as bar:
            task = bar.add_task("[blue]Working…", total=10)
            bar.update(task, completed=3, description="Chunk 1/3")
            assert bar.tasks[task].total == 10
    finally:
        BridgeProgress.ctx = None
    progress = [e for e in events(out) if e["type"] == "progress"]
    assert progress[0]["label"] == "Working…"
    assert progress[-1] == {"type": "progress", "current": 3, "total": 10, "label": "Chunk 1/3"}


# ---------------------------------------------------------------- adapter


def _command(ctx: typer.Context, file_paths: Optional[List[Path]] = typer.Argument(None),
             output: Optional[Path] = typer.Option(None, "--output"), mode: str = typer.Option("detailed")):
    return file_paths, output, mode, ctx.invoked_subcommand


def test_call_command_fills_defaults_and_coerces_paths():
    paths, output, mode, sub = call_command(_command, file_paths=["a.md"], output="out.md")
    assert paths == [Path("a.md")] and output == Path("out.md") and mode == "detailed" and sub is None
    with pytest.raises(TypeError):
        call_command(_command, nope=1)


def test_interactive_routes_input_and_typer_prompt():
    out = io.StringIO()
    stdin = io.StringIO('{"type":"answer","id":"p1","value":"+98912"}\n{"type":"answer","id":"p2","value":"s3cret"}\n')
    context = JobContext(Emitter(out), stdin)
    with interactive(context):
        assert input("Please enter your phone (or bot token): ") == "+98912"
        assert typer.prompt("api_hash", hide_input=True) == "s3cret"
    prompts = [e for e in events(out) if e["type"] == "prompt"]
    assert prompts[0]["kind"] == "phone" and prompts[1]["secret"] is True


def test_run_command_patches_progress_cost_and_reports_artifacts(ctx, tmp_path, monkeypatch):
    context, out = ctx
    module = types.ModuleType("fake_versline_cmd")

    class Tracker:
        total_input_tokens, total_output_tokens, total_cached_tokens, total_cost_usd = 10, 5, 0, 0.0
        avalai_request_ids: list = []

    def command(output: Path = typer.Option(...)):
        with module.Progress() as bar:
            bar.add_task("Writing", total=1)
        output.write_text("done", encoding="utf-8")
        module.print_cost_report(Tracker())

    module.Progress = object  # replaced during the run
    module.print_cost_report = lambda *a, **k: pytest.fail("real cost report must not run")
    module.command = command
    monkeypatch.setitem(sys.modules, "fake_versline_cmd", module)

    target = tmp_path / "result.md"
    produced = run_command(context, "fake_versline_cmd", "command", outputs=[tmp_path], output=target)
    assert produced == [target.resolve()]
    kinds = [e["type"] for e in events(out)]
    assert kinds == ["progress", "cost", "artifact"]
    assert events(out)[1]["input_tokens"] == 10
    assert module.Progress is object  # restored


# ---------------------------------------------------------------- manifest


def test_manifest_lists_every_tool_with_bilingual_labels():
    data = manifest()
    assert data["protocol"] == PROTOCOL_VERSION
    names = {t["name"] for t in data["tools"]}
    assert {"transcribe", "translate.file", "summarize.file", "qude", "qualcode", "research.outline",
            "research.full", "slides", "export", "telegram.archive", "telegram.taqrir", "telegram.contacts", "telegram.members", "telegram.chats", "organize.report",
            "config.get", "config.set", "obsidian.install"} <= names
    for item in data["tools"]:
        assert item["title"]["en"] and item["title"]["fa"], item["name"]
        for name, prop in item["params"].get("properties", {}).items():
            assert prop["x-label"]["en"] and prop["x-label"]["fa"], (item["name"], name)
            assert "anyOf" not in prop, (item["name"], name)
    json.dumps(data, ensure_ascii=False)


MINIMAL_PARAMS = {
    "transcribe": {"inputs": ["a.mp3"], "output": "a.md"},
    "translate.file": {"inputs": ["a.md"]},
    "translate.text": {"text": "hi"},
    "summarize.file": {"inputs": ["a.md"]},
    "summarize.text": {"text": "hi"},
    "qude": {"inputs": ["a.md"], "output_dir": "q"},
    "qualcode": {"inputs": ["a.md"], "output_dir": "q"},
    "research.outline": {"output": "o.md", "title": "T", "research_questions": ["Q?"]},
    "research.full": {"output": "f.md", "approved_outline_file": "o.md", "approve_outline": True},
    "slides": {"inputs": ["a.md"], "output_dir": "s"},
    "export": {"inputs": ["a.md"]},
    "export.install_browser": {},
    "telegram.archive": {"channel": "@c", "output": "out", "types": ["voice"], "summary": True},
    "telegram.taqrir": {"chat": "me", "output": "out"},
    "telegram.pack": {"archive_dir": "out"},
    "telegram.logout": {},
    "system.update": {},
    "organize.report": {"sources": ["src"], "copy_to": "reports"},
}


def test_every_tool_passes_only_options_its_command_accepts(tmp_path, monkeypatch):
    """Run each command-backed tool with run_command stubbed: every keyword must exist on the real command."""
    import importlib
    import inspect

    from versline.bridge import tools as tools_pkg

    calls = []

    def fake_run_command(ctx, module_name, func_name, outputs=(), **kwargs):
        func = getattr(importlib.import_module(module_name), func_name)
        unknown = set(kwargs) - set(inspect.signature(func).parameters)
        assert not unknown, f"{module_name}.{func_name}: {unknown}"
        calls.append(func_name)
        return []

    for module in vars(tools_pkg).values():
        if isinstance(module, types.ModuleType) and hasattr(module, "run_command"):
            monkeypatch.setattr(module, "run_command", fake_run_command)
    (tmp_path / "result.md").write_text("x")
    monkeypatch.chdir(tmp_path)

    registry = all_tools()
    for name, params in MINIMAL_PARAMS.items():
        item = registry[name]
        try:
            item.run(item.params.model_validate(params), JobContext(Emitter(io.StringIO()), None))
        except FileNotFoundError:
            pass  # text tools read the (stubbed, never written) result file
    assert len(calls) >= len(MINIMAL_PARAMS)


# ---------------------------------------------------------------- end to end


def test_summarize_file_end_to_end(tmp_path, monkeypatch):
    from versline.services import summarizer

    def fake_process(self, file_path, progress_callback=None, force=False):
        progress_callback(1, 2, "Chunk 1/2")
        print("a stray print from a service")
        return f"# Summary of {Path(file_path).name}\n"

    monkeypatch.setattr(summarizer.TextSummarizer, "process_file", fake_process)
    monkeypatch.chdir(tmp_path)
    note = tmp_path / "vault" / "lecture.md"
    note.parent.mkdir()
    note.write_text("long text", encoding="utf-8")
    output = tmp_path / "vault" / "lecture_summary.md"

    out = io.StringIO()
    code = run("summarize.file", {"params": {"inputs": [str(note)], "output": str(output), "mode": "outline"}},
               None, workdir=tmp_path / "work", out=out)
    stream = events(out)
    assert code == 0, stream
    assert output.read_text(encoding="utf-8") == "# Summary of lecture.md\n"
    kinds = [e["type"] for e in stream]
    assert kinds[0] == "hello" and kinds[-1] == "result"
    assert any(e["type"] == "progress" and e["label"] == "Chunk 1/2" for e in stream)
    assert any(e["type"] == "log" and "stray print" in e["message"] for e in stream)
    assert any(e["type"] == "cost" for e in stream)
    assert stream[-1]["data"]["outputs"] == [str(output.resolve())]
    assert sys.stdout is not None and not isinstance(sys.stdout, LogStream)


def test_unknown_tool_and_invalid_params(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = io.StringIO()
    assert run("nope", {}, None, out=out) == 2
    assert events(out)[-1]["code"] == "unknown_tool"
    out = io.StringIO()
    assert run("summarize.file", {"params": {"inputs": []}}, None, out=out) == 2
    assert events(out)[-1]["code"] == "invalid_params"


def test_config_set_and_get(tmp_path, monkeypatch):
    monkeypatch.setenv("VERSLINE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.chdir(tmp_path)
    out = io.StringIO()
    request = {"params": {"values": {"VERSLINE_LLM_PROVIDER": "OpenAI", "VERSLINE_LLM_API_KEY": "sk-1234567890"}}}
    assert run("config.set", request, None, workdir=tmp_path, out=out) == 0
    data = events(out)[-1]["data"]
    assert data["values"]["VERSLINE_LLM_PROVIDER"] == "OpenAI"
    assert data["values"]["VERSLINE_LLM_API_KEY"] != "sk-1234567890"
    assert "VERSLINE_LLM_API_KEY" in data["secrets_set"]

    out = io.StringIO()
    assert run("config.set", {"params": {"values": {"PATH": "x"}}}, None, workdir=tmp_path, out=out) == 1
    assert events(out)[-1]["code"] == "bad_input"
