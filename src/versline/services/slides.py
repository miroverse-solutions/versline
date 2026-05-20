import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services import ai
from versline.services.pricing import TokenTracker


DEFAULT_SLIDES_FONT_FAMILY = "Vazirmatn"
DEFAULT_SLIDES_FONT_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "assets" / "Vazirmatn[wght].ttf"
)

IMPRESS_JS_ASSET_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "assets" / "impress.min.js"
)
IMPRESS_JS_CDN_URL = "https://cdn.jsdelivr.net/npm/impress.js@2.0.0/js/impress.min.js"

_SLIDE_SIZES: Dict[str, tuple] = {
    "small":  ("720px", "480px"),
    "medium": ("960px", "640px"),
    "large":  ("1280px", "800px"),
}


def _ensure_impress_js_asset() -> Path:
    """Return path to impress.min.js, downloading it from CDN if not yet cached."""
    if IMPRESS_JS_ASSET_PATH.exists() and IMPRESS_JS_ASSET_PATH.stat().st_size > 0:
        return IMPRESS_JS_ASSET_PATH

    import urllib.request

    logger.info(f"Downloading impress.js from {IMPRESS_JS_CDN_URL} ...")
    try:
        with urllib.request.urlopen(IMPRESS_JS_CDN_URL, timeout=30) as response:  # noqa: S310
            content = response.read()
        IMPRESS_JS_ASSET_PATH.write_bytes(content)
        logger.info(f"impress.js cached at {IMPRESS_JS_ASSET_PATH} ({len(content):,} bytes)")
        return IMPRESS_JS_ASSET_PATH
    except Exception as exc:
        raise RuntimeError(
            f"Could not download impress.js: {exc}\n"
            f"Please manually download impress.js from {IMPRESS_JS_CDN_URL} "
            f"and place it at {IMPRESS_JS_ASSET_PATH}"
        ) from exc


@dataclass
class SlideDeckArtifacts:
    spatial_mapping: str
    index_html: str
    style_css: str
    main_ts: str


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\\s*|\\s*```$", re.DOTALL)


def _extract_fenced_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    current_lang: Optional[str] = None
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            if current_lang is None:
                current_lang = lang
                current_lines = []
            else:
                code = "\n".join(current_lines).strip()
                blocks.append((current_lang, code))
                current_lang = None
                current_lines = []
            continue

        if current_lang is not None:
            current_lines.append(raw_line)

    return blocks


def _strip_outer_code_fence(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def _try_parse_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    cleaned = _strip_outer_code_fence(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    return _try_parse_first_json_object(cleaned)


def _pick_file_value(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value

    files = payload.get("files")
    if isinstance(files, dict):
        for key in keys:
            value = files.get(key)
            if isinstance(value, str) and value.strip():
                return value

    return None


def extract_slide_artifacts(raw_response: str) -> SlideDeckArtifacts:
    if not raw_response or not raw_response.strip():
        raise ValueError("Model returned an empty response.")

    payload = _extract_json_payload(raw_response)
    if payload:
        spatial_mapping = str(payload.get("spatial_mapping") or payload.get("mapping") or "").strip()
        index_html = _pick_file_value(payload, "index_html", "index.html")
        style_css = _pick_file_value(payload, "style_css", "style.css")
        main_ts = _pick_file_value(payload, "main_ts", "main.ts", "main_typescript")

        if index_html and style_css and main_ts:
            return SlideDeckArtifacts(
                spatial_mapping=spatial_mapping,
                index_html=index_html.strip(),
                style_css=style_css.strip(),
                main_ts=main_ts.strip(),
            )

    html_blocks = []
    css_blocks = []
    ts_blocks = []

    for lang, code in _extract_fenced_blocks(raw_response):
        code = code.strip()
        if not code:
            continue
        if lang in {"html"}:
            html_blocks.append(code)
        elif lang in {"css", "scss"}:
            css_blocks.append(code)
        elif lang in {"ts", "typescript", "js", "javascript"}:
            ts_blocks.append(code)

    if html_blocks and css_blocks and ts_blocks:
        mapping_hint = raw_response.split("```", 1)[0].strip()
        return SlideDeckArtifacts(
            spatial_mapping=mapping_hint,
            index_html=html_blocks[0],
            style_css=css_blocks[0],
            main_ts=ts_blocks[0],
        )

    raise ValueError(
        "Could not parse generated slide files. Expected JSON payload or fenced html/css/ts blocks."
    )


def _is_external_url(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://") or normalized.startswith("//")


def strip_external_links_from_html(html_content: str) -> str:
    if not html_content.strip():
        return html_content

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup.find_all(["link", "script"]):
            attr = "href" if tag.name == "link" else "src"
            value = tag.get(attr)
            if isinstance(value, str) and _is_external_url(value):
                tag.decompose()
        return str(soup)
    except Exception:
        # Fallback regex cleanup if parser is unavailable.
        cleaned = re.sub(
            r"(?is)<link[^>]+href=[\"'](?:https?:)?//[^\"']+[\"'][^>]*>",
            "",
            html_content,
        )
        cleaned = re.sub(
            r"(?is)<script[^>]+src=[\"'](?:https?:)?//[^\"']+[\"'][^>]*>\s*</script>",
            "",
            cleaned,
        )
        return cleaned


def ensure_local_module_script_entry(html_content: str) -> str:
    if not html_content.strip():
        return html_content

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "html.parser")
        for script in soup.find_all("script"):
            src = script.get("src")
            if not isinstance(src, str):
                continue

            normalized = src.strip().lower()
            if not normalized or _is_external_url(normalized) or normalized.startswith("data:"):
                continue

            if normalized.endswith(".ts") or normalized.endswith(".js"):
                script["type"] = "module"

        return str(soup)
    except Exception:
        def _replace_script(match: re.Match[str]) -> str:
            src = match.group("src")
            normalized = src.strip().lower()
            if _is_external_url(normalized) or normalized.startswith("data:"):
                return match.group(0)
            if not (normalized.endswith(".ts") or normalized.endswith(".js")):
                return match.group(0)

            attrs = f"{match.group('attrs')}{match.group('tail')}"
            attrs = re.sub(
                r"(?is)\btype\s*=\s*(['\"]).*?\1",
                "",
                attrs,
                count=1,
            )
            return f'<script{attrs} type="module" src="{src}"></script>'

        return re.sub(
            r"(?is)<script(?P<attrs>[^>]*?)\bsrc\s*=\s*(['\"])(?P<src>[^\"']+)\2(?P<tail>[^>]*)>\s*</script>",
            _replace_script,
            html_content,
        )


def strip_external_imports_from_css(css_content: str) -> str:
    if not css_content.strip():
        return css_content

    cleaned = re.sub(
        r"(?im)^\s*@import\s+url\((?:[\"'])?(?:https?:)?//[^\)]*\);?\s*$",
        "",
        css_content,
    )
    cleaned = re.sub(
        r"(?im)^\s*@import\s+(?:[\"'])(?:https?:)?//[^\"']+(?:[\"']);?\s*$",
        "",
        cleaned,
    )
    return cleaned


def strip_conflicting_vazirmatn_face_from_css(css_content: str) -> str:
    if not css_content.strip():
        return css_content

    return re.sub(
        r"(?is)@font-face\s*\{[^\}]*url\((?:['\"])?(?:fonts/)?vazirmatn\.woff2(?:['\"])?\)[^\}]*\}\s*",
        "",
        css_content,
    )


def _css_font_format(font_path: Path) -> str:
    suffix = font_path.suffix.lower()
    if suffix == ".woff2":
        return "woff2"
    if suffix == ".woff":
        return "woff"
    if suffix == ".otf":
        return "opentype"
    return "truetype"


def _is_variable_font(font_path: Path) -> bool:
    name = font_path.name.lower()
    return "[wght]" in name or "variable" in name


def build_local_font_css(
    font_file_name: str,
    font_family: str,
    variable_font: bool,
    font_format: str,
) -> str:
    if variable_font:
        face_css = f"""@font-face {{
  font-family: '{font_family}';
    src: url('./{font_file_name}') format('{font_format}');
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
}}

@font-face {{
  font-family: '{font_family}';
    src: url('./{font_file_name}') format('{font_format}');
  font-weight: 100 900;
  font-style: italic;
  font-display: swap;
}}
"""
    else:
        face_css = f"""@font-face {{
  font-family: '{font_family}';
    src: url('./{font_file_name}') format('{font_format}');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}}

@font-face {{
  font-family: '{font_family}';
    src: url('./{font_file_name}') format('{font_format}');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}}
"""

    return (
        face_css
        + f"""
:root {{
  --versline-font-family: '{font_family}', 'Segoe UI', Tahoma, sans-serif;
}}

html,
body,
button,
input,
textarea,
select,
h1,
h2,
h3,
h4,
h5,
h6,
p,
li,
blockquote,
code,
pre {{
  font-family: var(--versline-font-family);
}}
"""
    )


def apply_local_font_bundle(
    artifacts: SlideDeckArtifacts,
    font_file_name: str,
    font_family: str,
    variable_font: bool,
    font_format: str,
) -> SlideDeckArtifacts:
    clean_html = strip_external_links_from_html(artifacts.index_html)
    clean_html = ensure_local_module_script_entry(clean_html)
    clean_css = strip_external_imports_from_css(artifacts.style_css)
    clean_css = strip_conflicting_vazirmatn_face_from_css(clean_css)
    font_css = build_local_font_css(font_file_name, font_family, variable_font, font_format)

    return SlideDeckArtifacts(
        spatial_mapping=artifacts.spatial_mapping,
        index_html=clean_html.strip(),
        style_css=(font_css + "\n\n" + clean_css.strip()).strip(),
        main_ts=artifacts.main_ts,
    )


def ensure_impress_script_tags(html_content: str) -> str:
    """Ensure `impress.min.js` script and `impress().init()` call are present before </body>."""
    if not html_content.strip():
        return html_content

    has_impress_src = "impress.min.js" in html_content
    has_impress_init = "impress().init()" in html_content

    if has_impress_src and has_impress_init:
        return html_content

    injection = ""
    if not has_impress_src:
        injection += '\n  <script src="impress.min.js"></script>'
    if not has_impress_init:
        injection += "\n  <script>impress().init();</script>"

    if "</body>" in html_content:
        return html_content.replace("</body>", f"{injection}\n</body>", 1)
    return html_content + injection


def apply_impress_js_bundle(
    artifacts: SlideDeckArtifacts,
    font_file_name: str,
    font_family: str,
    variable_font: bool,
    font_format: str,
) -> SlideDeckArtifacts:
    """Post-process artifacts for Impress.js mode.

    - Strips external CDN links/imports (keeps local asset references intact).
    - Injects local @font-face and broad font-family rule.
    - Ensures impress.js script tags are present.
    - Preserves the LLM-generated main_ts (no TypeScript runtime override).
    """
    clean_html = strip_external_links_from_html(artifacts.index_html)
    clean_html = ensure_impress_script_tags(clean_html)
    clean_css = strip_external_imports_from_css(artifacts.style_css)
    clean_css = strip_conflicting_vazirmatn_face_from_css(clean_css)
    font_css = build_local_font_css(font_file_name, font_family, variable_font, font_format)

    return SlideDeckArtifacts(
        spatial_mapping=artifacts.spatial_mapping,
        index_html=clean_html.strip(),
        style_css=(font_css + "\n\n" + clean_css.strip()).strip(),
        main_ts=artifacts.main_ts,
    )


def build_stable_slide_main_ts() -> str:
        return """interface SlideData {
    x: number;
    y: number;
    scale: number;
    el: HTMLElement;
}

class Presentation {
    private world: HTMLElement;
    private slides: SlideData[] = [];
    private currentIndex = 0;
    private progressEl: HTMLElement | null;

    constructor() {
        const worldEl =
            document.getElementById('world') ??
            document.getElementById('camera') ??
            document.querySelector('#viewport > div');

        if (!(worldEl instanceof HTMLElement)) {
            throw new Error('Slides container not found (expected #world or #camera).');
        }

        this.world = worldEl;
        this.progressEl = document.getElementById('progress');
        this.init();
    }

    private toNumber(value: string | undefined, fallback: number): number {
        const parsed = Number.parseFloat(value ?? '');
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    private init(): void {
        const slideElements = Array.from(document.querySelectorAll('.slide'));

        slideElements.forEach((node) => {
            const el = node as HTMLElement;
            const x = this.toNumber(el.dataset.x, 0);
            const y = this.toNumber(el.dataset.y, 0);
            const scale = Math.max(this.toNumber(el.dataset.scale, 1), 0.01);

            el.style.transform = `translate(-50%, -50%) translate3d(${x}px, ${y}px, 0px) scale(${scale})`;
            this.slides.push({ x, y, scale, el });
        });

        if (this.slides.length === 0) {
            return;
        }

        this.setupEventListeners();
        this.update();
    }

    private setupEventListeners(): void {
        const nextButton = document.getElementById('nextBtn') ?? document.getElementById('next');
        const prevButton = document.getElementById('prevBtn') ?? document.getElementById('prev');

        nextButton?.addEventListener('click', () => this.next());
        prevButton?.addEventListener('click', () => this.prev());

        window.addEventListener('keydown', (event) => {
            if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') {
                event.preventDefault();
                this.next();
            }

            if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
                event.preventDefault();
                this.prev();
            }

            if (event.key === 'Home') {
                this.currentIndex = 0;
                this.update();
            }

            if (event.key === 'End') {
                this.currentIndex = this.slides.length - 1;
                this.update();
            }
        });

        let touchStartX = 0;
        window.addEventListener('touchstart', (event) => {
            touchStartX = event.touches[0].clientX;
        });
        window.addEventListener('touchend', (event) => {
            const touchEndX = event.changedTouches[0].clientX;
            const delta = touchStartX - touchEndX;
            if (delta > 48) {
                this.next();
            }
            if (delta < -48) {
                this.prev();
            }
        });

        const rerender = () => this.update();
        window.addEventListener('resize', rerender);
        window.addEventListener('orientationchange', rerender);
    }

    private next(): void {
        if (this.currentIndex < this.slides.length - 1) {
            this.currentIndex += 1;
            this.update();
        }
    }

    private prev(): void {
        if (this.currentIndex > 0) {
            this.currentIndex -= 1;
            this.update();
        }
    }

    private update(): void {
        if (this.slides.length === 0) {
            return;
        }

        const current = this.slides[this.currentIndex];
        const baseScale = 1 / Math.max(current.scale, 0.01);

        const viewportWidth = Math.max(window.innerWidth - 32, 320);
        const viewportHeight = Math.max(window.innerHeight - 140, 260);
        const cardWidth = Math.max(current.el.offsetWidth, 1);
        const cardHeight = Math.max(current.el.offsetHeight, 1);

        const fitScale = Math.min(viewportWidth / cardWidth, viewportHeight / cardHeight, 1);
        const finalScale = baseScale * fitScale;

        const x = -current.x;
        const y = -current.y;
        const baseTransform = `scale(${finalScale}) translate3d(${x}px, ${y}px, 0px)`;
        this.world.style.transform = baseTransform;

        const activeRect = current.el.getBoundingClientRect();
        const activeCenterX = activeRect.left + activeRect.width / 2;
        const activeCenterY = activeRect.top + activeRect.height / 2;
        const viewportCenterX = window.innerWidth / 2;
        const viewportCenterY = window.innerHeight / 2;
        const correctionX = viewportCenterX - activeCenterX;
        const correctionY = viewportCenterY - activeCenterY;

        if (Math.abs(correctionX) > 0.5 || Math.abs(correctionY) > 0.5) {
            this.world.style.transform = `translate3d(${correctionX}px, ${correctionY}px, 0px) ${baseTransform}`;
        }

        this.slides.forEach((slide, index) => {
            const isActive = index === this.currentIndex;
            slide.el.classList.toggle('active', isActive);

            const listItems = Array.from(slide.el.querySelectorAll('li'));
            listItems.forEach((item, itemIndex) => {
                (item as HTMLElement).style.transitionDelay = isActive ? `${itemIndex * 0.08 + 0.2}s` : '0s';
            });
        });

        if (this.progressEl) {
            this.progressEl.innerText = `${this.currentIndex + 1} / ${this.slides.length}`;
        }
    }
}

window.addEventListener('DOMContentLoaded', () => {
    new Presentation();
});
"""


def build_responsive_slide_overrides_css(
    no_scroll: bool = True,
    uniform_size: bool = True,
    slide_size: str = "medium",
) -> str:
    size_key = slide_size.lower() if slide_size.lower() in _SLIDE_SIZES else "medium"
    max_width, max_height = _SLIDE_SIZES[size_key]

    slide_height_line = (
        "    height: min(var(--versline-slide-max-height), calc(100vh - var(--versline-slide-gutter-y))) !important;"
        if uniform_size
        else "    height: auto !important;"
    )
    slide_overflow_lines = (
        "    overflow: hidden;"
        if no_scroll
        else "    overflow: auto;\n    -webkit-overflow-scrolling: touch;"
    )

    return f"""
:root {{
    --versline-slide-max-width: {max_width};
    --versline-slide-max-height: {max_height};
    --versline-slide-gutter-x: 2rem;
    --versline-slide-gutter-y: 8.5rem;
}}

body {{
    overflow: hidden;
}}

#app {{
    width: 100vw !important;
    height: 100vh !important;
    min-height: 100vh !important;
    position: relative !important;
    overflow: hidden;
}}

#viewport {{
    width: 100% !important;
    height: 100% !important;
    position: relative !important;
    overflow: hidden;
}}

#world,
#camera {{
    top: 0 !important;
    left: 0 !important;
    position: absolute !important;
    transform-origin: 0 0;
    transition: none !important;
}}

.slide {{
    position: absolute !important;
    margin: 0 !important;
    margin-left: 0 !important;
    margin-top: 0 !important;
    top: 50% !important;
    left: 50% !important;
    width: min(var(--versline-slide-max-width), calc(100vw - var(--versline-slide-gutter-x))) !important;
    min-height: min(var(--versline-slide-max-height), calc(100vh - var(--versline-slide-gutter-y))) !important;
{slide_height_line}
    max-height: calc(100vh - var(--versline-slide-gutter-y)) !important;
{slide_overflow_lines}
    opacity: 0 !important;
    pointer-events: none;
}}

.slide.active {{
    opacity: 1 !important;
    pointer-events: auto;
}}

h1 {{
    font-size: clamp(1.8rem, 5vw, 4rem);
}}

h2 {{
    font-size: clamp(1.3rem, 3.8vw, 2.5rem);
}}

.controls {{
    max-width: calc(100vw - 1.5rem);
    flex-wrap: wrap;
    justify-content: center;
}}

#progress {{
    direction: ltr;
    unicode-bidi: isolate;
}}

@media (max-width: 900px) {{
    :root {{
        --versline-slide-gutter-x: 1rem;
        --versline-slide-gutter-y: 7.5rem;
    }}

    .slide {{
        padding: clamp(14px, 3vw, 24px) !important;
        border-radius: 6px;
    }}
}}

@media (max-width: 600px) {{
    :root {{
        --versline-slide-gutter-y: 7rem;
    }}

    .slide {{
        max-height: calc(100vh - var(--versline-slide-gutter-y)) !important;
        padding: 12px !important;
    }}

    .controls {{
        bottom: 18px !important;
        gap: 10px;
    }}

    button {{
        padding: 8px 14px;
    }}
}}
"""


def split_markdown_into_chunks(text: str, chunk_size: int) -> list[str]:
    """Split markdown into chunks of approximately *chunk_size* characters.

    Splits are made at heading boundaries (``# `` or ``## ``) to preserve
    section integrity.  If the full text fits in a single chunk it is returned
    as-is.
    """
    if chunk_size <= 0 or len(text) <= chunk_size:
        return [text]

    lines = text.splitlines(keepends=True)
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        is_heading = stripped.startswith("# ") or stripped.startswith("## ")
        if is_heading and current:
            sections.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("".join(current))

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for section in sections:
        section_len = len(section)
        if current_chunk and current_len + section_len > chunk_size:
            chunks.append("".join(current_chunk))
            current_chunk = [section]
            current_len = section_len
        else:
            current_chunk.append(section)
            current_len += section_len

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks if chunks else [text]


def find_last_slide_position(html_content: str) -> tuple[int, int]:
    """Return the (last_x, last_y) coordinates found among ``.slide`` elements."""
    x_vals = [int(v) for v in re.findall(r'data-x=["\'](-?\d+)["\']', html_content)]
    y_vals = [int(v) for v in re.findall(r'data-y=["\'](-?\d+)["\']', html_content)]
    last_x = max(x_vals) if x_vals else 0
    last_y = y_vals[-1] if y_vals else 0
    return last_x, last_y


def inject_slides_into_deck(existing_html: str, new_slides_html: str) -> str:
    """Append *new_slides_html* into the world/camera container of *existing_html*.

    Tries to locate ``#world`` or ``#camera`` via BeautifulSoup and appends there.
    Falls back to inserting before ``</body>`` when the parser is unavailable.
    """
    if not new_slides_html.strip():
        return existing_html

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(existing_html, "html.parser")
        container = (
            soup.find(id="impress")
            or soup.find(id="world")
            or soup.find(id="camera")
            or soup.select_one("#viewport > div")
            or soup.find("body")
        )
        if container:
            fragment = BeautifulSoup(new_slides_html, "html.parser")
            for el in list(fragment.find_all("div", class_=lambda c: c and "slide" in c)):
                container.append(el)
            return str(soup)
    except Exception:
        pass

    if "</body>" in existing_html:
        return existing_html.replace("</body>", f"\n{new_slides_html.strip()}\n</body>", 1)
    return existing_html + "\n" + new_slides_html.strip()


def extract_new_slides_payload(raw_response: str) -> str:
    """Parse the LLM response for chunk mode and return the ``new_slides_html`` value."""
    cleaned = _strip_outer_code_fence(raw_response)
    payload = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            payload = parsed
    except json.JSONDecodeError:
        payload = _try_parse_first_json_object(cleaned)

    if payload:
        value = payload.get("new_slides_html") or payload.get("slides_html") or payload.get("html")
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Fallback: extract fenced html blocks
    for lang, code in _extract_fenced_blocks(raw_response):
        if lang in {"html"} and "slide" in code.lower():
            return code.strip()

    # Last resort: return the raw response as-is and let the caller handle it
    return raw_response.strip()


def apply_runtime_and_responsive_defaults(
    artifacts: SlideDeckArtifacts,
    no_scroll: bool = True,
    uniform_size: bool = True,
    slide_size: str = "medium",
) -> SlideDeckArtifacts:
        responsive_overrides = build_responsive_slide_overrides_css(
            no_scroll=no_scroll,
            uniform_size=uniform_size,
            slide_size=slide_size,
        ).strip()
        style_css = (artifacts.style_css.strip() + "\n\n" + responsive_overrides).strip()

        return SlideDeckArtifacts(
                spatial_mapping=artifacts.spatial_mapping,
                index_html=artifacts.index_html,
                style_css=style_css,
                main_ts=build_stable_slide_main_ts().strip(),
        )


def write_vite_project_files(project_dir: Path, single_file: bool) -> None:
    package = {
        "name": "versline-slide-deck",
        "private": True,
        "version": "0.0.1",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
        },
        "devDependencies": {
            "typescript": "^5.6.3",
            "vite": "^5.4.8",
        },
    }

    if single_file:
        package["devDependencies"]["vite-plugin-singlefile"] = "^2.1.0"

    (project_dir / "package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    tsconfig_text = """{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["main.ts", "vite.config.ts"]
}
"""
    (project_dir / "tsconfig.json").write_text(tsconfig_text, encoding="utf-8")

    if single_file:
        vite_config = """import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

export default defineConfig({
  base: './',
  plugins: [viteSingleFile()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
"""
    else:
        vite_config = """import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
"""

    (project_dir / "vite.config.ts").write_text(vite_config, encoding="utf-8")


class MarkdownSlideDeckGenerator:
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        proxy: Optional[str] = None,
        prompt_path: Optional[str] = None,
        font_path: Optional[str] = None,
        font_family: str = DEFAULT_SLIDES_FONT_FAMILY,
        include_all_content: bool = False,
        verbatim_text: bool = False,
        no_scroll: bool = True,
        uniform_size: bool = True,
        slide_size: str = "medium",
        use_impress: bool = False,
        user_note: Optional[str] = None,
    ):
        self.provider = provider or settings.llm.provider or "Google"
        self.model = model or settings.llm.model
        self.api_key = api_key or settings.llm.api_key
        self.api_endpoint = api_endpoint or settings.llm.api_endpoint
        self.proxy = proxy or settings.llm.proxy
        self.prompt_path = Path(prompt_path) if prompt_path else None
        self.font_path = Path(font_path).expanduser() if font_path else None
        self.font_family = (font_family or DEFAULT_SLIDES_FONT_FAMILY).strip()
        self.include_all_content = include_all_content
        self.verbatim_text = verbatim_text
        self.no_scroll = no_scroll
        self.uniform_size = uniform_size
        self.slide_size = slide_size.lower() if slide_size.lower() in _SLIDE_SIZES else "medium"
        self.use_impress = use_impress
        self.user_note = user_note
        self.tracker = TokenTracker()
        self.prompt_template = self._load_prompt_template()
        self.add_prompt_template = self._load_add_prompt_template()

    def _load_prompt_template(self) -> str:
        if self.prompt_path:
            if not self.prompt_path.exists():
                raise FileNotFoundError(f"Prompt file not found: {self.prompt_path}")
            return self.prompt_path.read_text(encoding="utf-8")
        if self.use_impress:
            return load_prompt("slides_impress_prompt.md")
        return load_prompt("slides_prompt.md")

    def _load_add_prompt_template(self) -> str:
        if self.use_impress:
            return load_prompt("slides_impress_add_prompt.md")
        return load_prompt("slides_add_prompt.md")

    def _resolve_provider_name(self) -> str:
        normalized = str(self.provider).strip().lower()
        aliases = {
            "google": "gemini",
            "custom": "openaicompatible",
            "openai-compatible": "openaicompatible",
            "openai_compatible": "openaicompatible",
        }
        return aliases.get(normalized, normalized)

    def _build_avalai_extra_body(self) -> Optional[Dict[str, str]]:
        explicit_provider = (
            (settings.llm.avalai_provider if hasattr(settings.llm, "avalai_provider") else None)
            or None
        )
        if explicit_provider:
            return {"provider": str(explicit_provider).strip().lower()}

        model = str(self.model or "").strip().lower()
        if model.startswith("gemini"):
            return {"provider": "google"}
        if model.startswith("claude"):
            return {"provider": "anthropic"}
        if model.startswith(("gpt", "o1", "o3")):
            return {"provider": "openai"}
        return None

    def _render_prompt(self, markdown_text: str) -> str:
        extra_section = self._build_extra_instructions_section()
        template = self.prompt_template
        if extra_section:
            marker = "# Markdown Input"
            if marker in template:
                template = template.replace(marker, extra_section + "\n\n" + marker, 1)
        return template.replace("{{markdown_content}}", markdown_text)

    def _build_extra_instructions_section(self) -> str:
        instructions = []
        if self.include_all_content:
            instructions.append(
                "CONTENT COMPLETENESS: You MUST include every piece of content from the input markdown "
                "in the generated slides. Do not omit, skip, summarize, or condense any section, heading, "
                "list item, code block, or paragraph. Create as many additional slides as needed to accommodate all content."
            )
        if self.verbatim_text:
            instructions.append(
                "VERBATIM TEXT: Every text string that appears in the slides MUST be copied word-for-word "
                "from the input markdown. Do not rephrase, paraphrase, reword, or alter any text. "
                "Only text that appears literally in the source may be used in the slides."
            )
        if self.no_scroll:
            instructions.append(
                "NO-SCROLL LAYOUT: Each slide MUST be designed so that ALL of its content is fully visible "
                "within a single viewport height with zero scrolling. If a section contains more content than "
                "fits in one slide, split it across multiple slides. Never rely on scrolling to reveal content within a slide."
            )
        if self.uniform_size:
            instructions.append(
                "UNIFORM SLIDE DIMENSIONS: All slides MUST have identical dimensions. Do not vary the size, "
                "scale factor, or padding between slides. Set data-scale=\"1\" on all slide elements."
            )
        if self.user_note:
            instructions.append(f"USER NOTE: {self.user_note}")
        if not instructions:
            return ""
        lines = "\n".join(f"- {instr}" for instr in instructions)
        return f"# Additional Content & Layout Requirements\n{lines}"

    def _resolve_font_source_path(self) -> Path:
        candidate = self.font_path or DEFAULT_SLIDES_FONT_PATH
        resolved = candidate.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Font file not found: {resolved}")
        return resolved

    def _generate_with_gemini(self, prompt: str) -> str:
        client = ai.configure_gemini(
            ai.LLMSettings(
                provider="gemini",
                model=self.model,
                api_key=self.api_key,
                api_endpoint=self.api_endpoint,
                proxy=self.proxy,
            )
        )
        if client is None:
            raise RuntimeError("Failed to configure Gemini client.")

        from google.genai.types import GenerateContentConfig

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=GenerateContentConfig(
                response_mime_type="application/json",
                temperature=1,
            ),
        )

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            self.tracker.add_usage(
                int(response.usage_metadata.prompt_token_count or 0),
                int(response.usage_metadata.candidates_token_count or 0),
            )

        return str(response.text or "")

    def _generate_with_openai_compatible(self, provider: str, prompt: str) -> str:
        effective_endpoint = self.api_endpoint
        if provider == "avalai" and not effective_endpoint:
            effective_endpoint = "https://api.avalai.ir/v1"
        if provider == "openrouter" and not effective_endpoint:
            effective_endpoint = "https://openrouter.ai/api/v1"

        client = ai.configure_openai(
            ai.LLMSettings(
                provider=provider,
                model=self.model,
                api_key=self.api_key,
                api_endpoint=effective_endpoint,
                proxy=self.proxy,
            )
        )
        if client is None:
            raise RuntimeError("Failed to configure OpenAI-compatible client.")

        create_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a senior frontend architect that returns strict JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 1,
            "response_format": {"type": "json_object"},
        }

        if provider == "avalai":
            extra_body = self._build_avalai_extra_body()
            if extra_body:
                create_kwargs["extra_body"] = extra_body

        try:
            if provider == "avalai" and hasattr(client.chat.completions, "with_raw_response"):
                raw = client.chat.completions.with_raw_response.create(**create_kwargs)
                request_id = raw.headers.get("x-request-id")
                if request_id:
                    self.tracker.add_avalai_request(request_id)
                completion = raw.parse()
            else:
                completion = client.chat.completions.create(**create_kwargs)
        except Exception:
            create_kwargs.pop("response_format", None)
            completion = client.chat.completions.create(**create_kwargs)

        if completion.usage:
            self.tracker.add_usage(
                int(completion.usage.prompt_tokens or 0),
                int(completion.usage.completion_tokens or 0),
            )

        return str(completion.choices[0].message.content or "")

    def _request_generation(self, prompt: str, max_retries: int = 3) -> str:
        provider = self._resolve_provider_name()

        for attempt in range(max_retries):
            try:
                if provider == "gemini":
                    return self._generate_with_gemini(prompt)
                if provider in {"openai", "openrouter", "avalai", "openaicompatible"}:
                    return self._generate_with_openai_compatible(provider, prompt)
                return self._generate_with_openai_compatible("openaicompatible", prompt)
            except Exception as error:
                if attempt >= max_retries - 1:
                    raise RuntimeError(f"Slide generation failed after retries: {error}") from error
                backoff_seconds = 2 * (attempt + 1)
                logger.warning(
                    f"Slide generation failed (attempt {attempt + 1}/{max_retries}): {error}. "
                    f"Retrying in {backoff_seconds}s."
                )
                time.sleep(backoff_seconds)

        raise RuntimeError("Slide generation failed.")

    def _render_add_prompt(self, markdown_chunk: str, style_css: str, last_x: int, last_y: int) -> str:
        return (
            self.add_prompt_template
            .replace("{{existing_style_css}}", style_css)
            .replace("{{last_x}}", str(last_x))
            .replace("{{last_y}}", str(last_y))
            .replace("{{markdown_content}}", markdown_chunk)
        )

    def _generate_add_slides_request(
        self,
        markdown_chunk: str,
        style_css: str,
        last_x: int,
        last_y: int,
    ) -> str:
        prompt = self._render_add_prompt(markdown_chunk, style_css, last_x, last_y)
        raw = self._request_generation(prompt)
        return extract_new_slides_payload(raw)

    def _run_command(self, command: list[str], cwd: Path) -> None:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            details = stderr or stdout or "Unknown error"
            raise RuntimeError(f"Command failed: {' '.join(command)}\n{details}")

    def _build_with_vite(self, deck_dir: Path, single_file: bool, install_deps: bool) -> Path:
        npm_path = shutil.which("npm")
        if not npm_path:
            raise RuntimeError("npm is required for --build but was not found in PATH.")

        write_vite_project_files(deck_dir, single_file=single_file)

        if install_deps:
            self._run_command([npm_path, "install"], cwd=deck_dir)
        elif not (deck_dir / "node_modules").exists():
            raise RuntimeError(
                "node_modules not found. Run with --install-deps or install dependencies manually."
            )

        self._run_command([npm_path, "run", "build"], cwd=deck_dir)
        return deck_dir / "dist"

    def generate_from_markdown(
        self,
        input_path: str,
        output_dir: str,
        build: bool = False,
        single_file: bool = False,
        install_deps: bool = True,
        chunk_size: int = 0,
    ) -> Dict[str, str]:
        source_path = Path(input_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Input markdown file not found: {source_path}")

        markdown_text = source_path.read_text(encoding="utf-8")
        if not markdown_text.strip():
            raise ValueError("Input markdown file is empty.")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        deck_dir = Path(output_dir) / f"{source_path.stem}_slides_{timestamp}"
        deck_dir.mkdir(parents=True, exist_ok=True)

        chunks = split_markdown_into_chunks(markdown_text, chunk_size)
        logger.info(f"Generating slide deck in {len(chunks)} chunk(s) (chunk_size={chunk_size or 'unlimited'}).")

        # --- First chunk: full deck generation ---
        rendered_prompt = self._render_prompt(chunks[0])
        raw_response = self._request_generation(rendered_prompt)
        artifacts = extract_slide_artifacts(raw_response)

        font_source_path = self._resolve_font_source_path()
        font_target_path = deck_dir / font_source_path.name
        shutil.copy2(font_source_path, font_target_path)

        if self.use_impress:
            impress_js_source = _ensure_impress_js_asset()
            impress_js_target = deck_dir / "impress.min.js"
            shutil.copy2(impress_js_source, impress_js_target)
            artifacts = apply_impress_js_bundle(
                artifacts=artifacts,
                font_file_name=font_target_path.name,
                font_family=self.font_family,
                variable_font=_is_variable_font(font_source_path),
                font_format=_css_font_format(font_source_path),
            )
        else:
            artifacts = apply_local_font_bundle(
                artifacts=artifacts,
                font_file_name=font_target_path.name,
                font_family=self.font_family,
                variable_font=_is_variable_font(font_source_path),
                font_format=_css_font_format(font_source_path),
            )
            artifacts = apply_runtime_and_responsive_defaults(
                artifacts,
                no_scroll=self.no_scroll,
                uniform_size=self.uniform_size,
                slide_size=self.slide_size,
            )

        # --- Subsequent chunks: append slides only ---
        for chunk_idx, chunk in enumerate(chunks[1:], start=2):
            logger.info(f"Processing chunk {chunk_idx}/{len(chunks)}: adding slides...")
            last_x, last_y = find_last_slide_position(artifacts.index_html)
            new_slides_html = self._generate_add_slides_request(
                markdown_chunk=chunk,
                style_css=artifacts.style_css,
                last_x=last_x,
                last_y=last_y,
            )
            updated_html = inject_slides_into_deck(artifacts.index_html, new_slides_html)
            artifacts = SlideDeckArtifacts(
                spatial_mapping=artifacts.spatial_mapping,
                index_html=updated_html,
                style_css=artifacts.style_css,
                main_ts=artifacts.main_ts,
            )

        index_path = deck_dir / "index.html"
        style_path = deck_dir / "style.css"
        main_path = deck_dir / "main.ts"
        mapping_path = deck_dir / "spatial-mapping.md"

        index_path.write_text(artifacts.index_html + "\n", encoding="utf-8")
        style_path.write_text(artifacts.style_css + "\n", encoding="utf-8")
        main_path.write_text(artifacts.main_ts + "\n", encoding="utf-8")
        mapping_path.write_text((artifacts.spatial_mapping or "No mapping summary provided.") + "\n", encoding="utf-8")

        result: Dict[str, str] = {
            "deck_dir": str(deck_dir),
            "index_html": str(index_path),
            "style_css": str(style_path),
            "main_ts": str(main_path),
            "spatial_mapping": str(mapping_path),
            "font_file": str(font_target_path),
        }

        if self.use_impress:
            result["impress_js"] = str(deck_dir / "impress.min.js")

        if build:
            dist_dir = self._build_with_vite(
                deck_dir=deck_dir,
                single_file=single_file,
                install_deps=install_deps,
            )
            result["dist_dir"] = str(dist_dir)

        return result
