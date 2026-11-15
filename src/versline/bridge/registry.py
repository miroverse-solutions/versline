"""Tool registry: every bridge tool is a Pydantic parameter model plus a run function.

The manifest (``versline bridge info``) is generated from the models, including bilingual labels and UI
hints, so clients can render a form for any tool without knowing it in advance:

    x-label   {"en": ..., "fa": ...}         field label
    x-help    {"en": ..., "fa": ...}         field help text
    x-widget  file | files | folder | text | textarea | secret | output-file | output-folder | date | tags
    x-accept  [".md", ".pdf", ...]           file extensions a file widget accepts
    x-advanced true                          hide behind an "advanced" toggle
    x-output  "{dir}/{stem}_summary.md"      default for output widgets, from the first input
    x-choices {value: {"en": ..., "fa": ...}} labels for enum values
"""
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, Field

Text = Dict[str, str]


def tr(en: str, fa: str) -> Text:
    return {"en": en, "fa": fa}


def F(
    default: Any = ...,
    *,
    en: str,
    fa: str,
    help_en: Optional[str] = None,
    help_fa: Optional[str] = None,
    widget: Optional[str] = None,
    accept: Optional[List[str]] = None,
    advanced: bool = False,
    output: Optional[str] = None,
    choices: Optional[Dict[str, Text]] = None,
    **kwargs: Any,
) -> Any:
    """A Pydantic Field with the bridge's UI hints."""
    extra: Dict[str, Any] = {"x-label": tr(en, fa)}
    if help_en or help_fa:
        extra["x-help"] = tr(help_en or "", help_fa or help_en or "")
    if widget:
        extra["x-widget"] = widget
    if accept:
        extra["x-accept"] = accept
    if advanced:
        extra["x-advanced"] = True
    if output:
        extra["x-output"] = output
    if choices:
        extra["x-choices"] = choices
    return Field(default, description=help_en, json_schema_extra=extra, **kwargs)


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class Tool:
    name: str
    category: str
    title: Text
    description: Text
    params: Type[Params]
    run: Callable[[Any, Any], Any]
    needs_llm: bool = True
    interactive: bool = False
    hidden: bool = False
    tags: List[str] = dc_field(default_factory=list)

    def manifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "needs_llm": self.needs_llm,
            "interactive": self.interactive,
            "hidden": self.hidden,
            "tags": self.tags,
            "params": simplify_schema(self.params.model_json_schema()),
        }


_REGISTRY: Dict[str, Tool] = {}


def tool(
    name: str,
    *,
    category: str,
    title: Text,
    description: Text,
    params: Type[Params],
    needs_llm: bool = True,
    interactive: bool = False,
    hidden: bool = False,
    tags: Optional[List[str]] = None,
) -> Callable:
    def register(func: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"Duplicate bridge tool: {name}")
        _REGISTRY[name] = Tool(name, category, title, description, params, func, needs_llm, interactive, hidden, tags or [])
        return func

    return register


def all_tools() -> Dict[str, Tool]:
    from versline.bridge import tools  # noqa: F401  (registers every tool module)

    return dict(_REGISTRY)


def get_tool(name: str) -> Tool:
    tools = all_tools()
    if name not in tools:
        raise KeyError(name)
    return tools[name]


def simplify_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten Pydantic's Optional (anyOf [X, null]) into {type: X, nullable: true} and inline enum $refs."""
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = defs.get(node["$ref"].split("/")[-1], {})
                merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
                return resolve(merged)
            if "anyOf" in node:
                options = [o for o in node["anyOf"] if o.get("type") != "null"]
                if len(options) == 1 and len(options) < len(node["anyOf"]):
                    rest = {k: v for k, v in node.items() if k != "anyOf"}
                    return resolve({**options[0], **rest, "nullable": True})
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    simplified = resolve(schema)
    simplified.pop("title", None)
    for prop in simplified.get("properties", {}).values():
        prop.pop("title", None)
    return simplified
