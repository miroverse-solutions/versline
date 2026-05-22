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
    Path(__file__).resolve().parent.parent / "resources" / "assets" /
    "Vazirmatn[wght].woff2"
)
DEFAULT_SLIDES_FONT_FORMAT = "woff2"

IMPRESS_FONT_FAMILY = "Vazirmatn"
IMPRESS_FONT_PATH = DEFAULT_SLIDES_FONT_PATH
IMPRESS_FONT_FORMAT = DEFAULT_SLIDES_FONT_FORMAT

_SLIDE_SIZES = {
    "small":  ("720px",  "405px"),
    "medium": ("960px",  "540px"),
    "large":  ("1280px", "720px"),
    "xlarge": ("1600px", "900px"),
}


@dataclass
class SlideDeckArtifacts:
    spatial_mapping: str
    index_html: str
    style_css: str
    main_ts: str
    slides_json: str = ""


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)


def _strip_outer_code_fence(text: str) -> str:
    """Remove a single wrapping ```json ... ``` fence if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()


def _try_parse_first_json_object(text: str) -> Optional[dict]:
    """Find and parse the first JSON object that appears in *text*."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _pick_file_value(payload: dict, *keys: str) -> str:
    """Return the first non-empty string value found for any of *keys*."""
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def extract_slide_artifacts(raw_response: str) -> Optional[SlideDeckArtifacts]:
    """Parse the raw LLM response and return a :class:`SlideDeckArtifacts`.

    Handles three response shapes:

    1. Clean JSON object (possibly wrapped in a single ```json … ``` fence).
    2. A JSON object embedded somewhere inside a larger prose response.
    3. Fallback: HTML/CSS/TypeScript extracted from separate ``` code blocks.
    """
    cleaned = _strip_outer_code_fence(raw_response)

    payload = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            payload = parsed
    except json.JSONDecodeError:
        payload = _try_parse_first_json_object(cleaned)

    if payload:
        spatial_mapping = _pick_file_value(
            payload, "spatial_mapping", "layout_strategy", "mapping"
        )
        index_html = _pick_file_value(payload, "index_html", "index.html", "html")
        style_css = _pick_file_value(payload, "style_css", "style.css")
        main_ts = _pick_file_value(payload, "main_ts", "main.ts", "main_typescript")

        # Extract slides_json — may be a nested object or a JSON string
        slides_json_raw = payload.get("slides_json")
        slides_json = ""
        if isinstance(slides_json_raw, dict):
            slides_json = json.dumps(slides_json_raw, ensure_ascii=False, indent=2)
        elif isinstance(slides_json_raw, str) and slides_json_raw.strip():
            slides_json = slides_json_raw.strip()

        if index_html and style_css and main_ts:
            return SlideDeckArtifacts(
                spatial_mapping=spatial_mapping,
                index_html=index_html.strip(),
                style_css=style_css.strip(),
                main_ts=main_ts.strip(),
                slides_json=slides_json,
            )

    html_blocks = []
    css_blocks = []
    ts_blocks = []

    fence_pattern = re.compile(
        r"```(?P<lang>\w+)?\n(?P<code>.*?)```", re.DOTALL
    )
    for match in fence_pattern.finditer(raw_response):
        lang = (match.group("lang") or "").lower()
        code = match.group("code").strip()
        if lang in ("html",):
            html_blocks.append(code)
        elif lang in ("css",):
            css_blocks.append(code)
        elif lang in ("typescript", "ts"):
            ts_blocks.append(code)

    if html_blocks and css_blocks and ts_blocks:
        return SlideDeckArtifacts(
            spatial_mapping="",
            index_html=html_blocks[0],
            style_css=css_blocks[0],
            main_ts=ts_blocks[0],
        )

    return None


def strip_external_links_from_html(html_content: str) -> str:
    """Remove CDN / external stylesheet and script tags from *html_content*.

    Keeps ``<link>`` and ``<script>`` elements that reference local paths
    (i.e. do *not* start with ``http://``, ``https://``, or ``//``).
    """
    html_content = re.sub(
        r'<link[^>]+href=["\']https?://[^"\']*["\'][^>]*/?>',
        "",
        html_content,
        flags=re.IGNORECASE,
    )
    html_content = re.sub(
        r'<link[^>]+href=["\']//[^"\']*["\'][^>]*/?>',
        "",
        html_content,
        flags=re.IGNORECASE,
    )
    html_content = re.sub(
        r'<script[^>]+src=["\']https?://[^"\']*["\'][^>]*>.*?</script>',
        "",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html_content = re.sub(
        r'<script[^>]+src=["\']//[^"\']*["\'][^>]*>.*?</script>',
        "",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html_content


def strip_external_imports_from_css(css_content: str) -> str:
    """Remove ``@import url(...)`` rules that reference external (CDN) URLs."""
    css_content = re.sub(
        r"@import\s+url\(['\"]?https?://[^)'\"\s]+['\"]?\)\s*;?",
        "",
        css_content,
        flags=re.IGNORECASE,
    )
    css_content = re.sub(
        r'@import\s+["\']https?://[^"\']+["\']\s*;?',
        "",
        css_content,
        flags=re.IGNORECASE,
    )
    return css_content


def strip_conflicting_vazirmatn_face_from_css(css_content: str) -> str:
    """Remove any ``@font-face`` block for Vazirmatn from LLM-generated CSS.

    versline injects its own bundled @font-face rule; the LLM-generated one
    typically points to a CDN or a wrong local path, which would conflict.
    """
    return re.sub(
        r"@font-face\s*\{[^}]*font-family\s*:\s*['\"]?Vazirmatn['\"]?[^}]*\}",
        "",
        css_content,
        flags=re.IGNORECASE | re.DOTALL,
    )


def build_local_font_css(
    font_file_name: str,
    font_family: str,
    variable_font: bool,
    font_format: str,
) -> str:
    """Return a ``@font-face`` block and a broad ``font-family`` rule.

    The ``@font-face`` references *font_file_name* as a local asset (no CDN).
    The broad rule applies ``font-family`` to ``*`` so every element inherits it
    without relying on the LLM to have set ``font-family`` consistently.
    """
    if variable_font:
        src_line = (
            f"  src: url('{font_file_name}') format('{font_format}');\n"
            f"  font-weight: 100 900;\n"
            f"  font-style: normal;\n"
        )
    else:
        src_line = (
            f"  src: url('{font_file_name}') format('{font_format}');\n"
        )

    return (
        f"@font-face {{\n"
        f"  font-family: '{font_family}';\n"
        f"{src_line}"
        f"}}\n\n"
        f"* {{ font-family: '{font_family}', sans-serif; }}"
    )


def ensure_impress_script_tags(html_content: str) -> str:
    """Guarantee that ``impress.js`` script tags are present in *html_content*.

    - Ensures ``<script src="impress.js">`` (or ``impress.min.js``) exists.
    - Adds ``<script>impress().init();</script>`` unless already present.
    The function is idempotent: calling it twice produces the same result.
    """
    if not html_content.strip():
        return html_content

    has_impress_src = bool(
        re.search(r'src=["\']impress(?:\.min)?\.js["\']', html_content)
    )
    if not has_impress_src:
        impress_tag = '\n  <script src="impress.min.js"></script>'
        if "</body>" in html_content:
            html_content = html_content.replace(
                "</body>", f"{impress_tag}\n</body>", 1
            )
        else:
            html_content += impress_tag

    has_init = bool(re.search(r"impress\(\)\.init\(\)", html_content))
    if not has_init:
        init_tag = "\n  <script>impress().init();</script>"
        if "</body>" in html_content:
            html_content = html_content.replace(
                "</body>", f"{init_tag}\n</body>", 1
            )
        else:
            html_content += init_tag

    return html_content


def inject_impress_slide(html_content: str, slide_html: str) -> str:
    """Append *slide_html* inside the ``#impress`` container in *html_content*."""
    injection = slide_html.strip()
    if not injection:
        return html_content
    if 'id="impress"' in html_content:
        close_idx = html_content.rfind("</div>")
        if close_idx != -1:
            return html_content[:close_idx] + "\n" + injection + "\n" + html_content[close_idx:]
    return html_content + "\n" + injection


def inject_slides_into_deck(html_content: str, new_slides_html: str) -> str:
    """Append *new_slides_html* inside the slides container of *html_content*."""
    injection = new_slides_html.strip()
    if not injection:
        return html_content
    if "</body>" in html_content:
        return html_content.replace("</body>", f"{injection}\n</body>", 1)
    return html_content + injection


def ensure_impress_json_module_setup(html_content: str) -> str:
    """Set up HTML for JSON-based impress.js mode.

    - Removes inline ``impress().init()`` (main.ts calls it after building slides from JSON).
    - Ensures ``<script src="impress.js">`` is present as a regular (non-module) script.
    - Ensures ``<script type="module" src="main.ts">`` is present so Vite can bundle the
      TypeScript entry point that imports ``slides.json`` and initialises the presentation.
    """
    if not html_content.strip():
        return html_content

    # Remove inline impress().init() — main.ts calls it after building slides from JSON
    html_content = re.sub(
        r'(?is)<script[^>]*>\s*impress\(\)\.init\(\)\s*;?\s*</script>',
        '',
        html_content,
    )

    # Ensure impress.js regular script is present
    has_impress_src = bool(re.search(r'src=["\']impress(?:\.min)?\.js["\']', html_content))
    if not has_impress_src:
        impress_tag = '\n  <script src="impress.js"></script>'
        if "</body>" in html_content:
            html_content = html_content.replace("</body>", f"{impress_tag}\n</body>", 1)
        else:
            html_content += impress_tag

    # Ensure main.ts module script is present
    has_main_ts = bool(re.search(r'src=["\']main\.ts["\']', html_content))
    if not has_main_ts:
        module_tag = '\n  <script type="module" src="main.ts"></script>'
        if "</body>" in html_content:
            html_content = html_content.replace("</body>", f"{module_tag}\n</body>", 1)
        else:
            html_content += module_tag

    return html_content


def build_stable_impress_main_ts_json_loader() -> str:
    """Return a stable TypeScript entry point for the JSON-based impress.js mode.

    Imports slide data from ``./slides.json``, builds ``<div class="step slide">``
    elements dynamically, and calls ``impress().init()`` once slides are in the DOM.
    Vite (with or without ``vite-plugin-singlefile``) handles the JSON import at build
    time, so both dev-server and single-file production builds work correctly.
    """
    return """import slidesData from './slides.json';

interface SlideEntry {
  id: string;
  x?: number;
  y?: number;
  z?: number;
  scale?: number;
  rotate?: number;
  rotate_x?: number;
  rotate_y?: number;
  rotate_z?: number;
  html: string;
}

interface SlidesData {
  slides: SlideEntry[];
  overview?: { x?: number; y?: number; z?: number; scale?: number };
}

function buildSlides(): void {
  const container = document.getElementById('impress');
  if (!container) return;

  const data = slidesData as unknown as SlidesData;

  data.slides.forEach((slide) => {
    const el = document.createElement('div');
    el.className = 'step slide';
    el.id = slide.id;
    if (slide.x !== undefined) el.setAttribute('data-x', String(slide.x));
    if (slide.y !== undefined) el.setAttribute('data-y', String(slide.y));
    if (slide.z !== undefined) el.setAttribute('data-z', String(slide.z));
    if (slide.scale !== undefined) el.setAttribute('data-scale', String(slide.scale));
    if (slide.rotate !== undefined) el.setAttribute('data-rotate', String(slide.rotate));
    if (slide.rotate_x !== undefined) el.setAttribute('data-rotate-x', String(slide.rotate_x));
    if (slide.rotate_y !== undefined) el.setAttribute('data-rotate-y', String(slide.rotate_y));
    if (slide.rotate_z !== undefined) el.setAttribute('data-rotate-z', String(slide.rotate_z));
    el.innerHTML = slide.html;
    container.appendChild(el);
  });

  const overview = data.overview;
  if (overview) {
    const el = document.createElement('div');
    el.id = 'overview';
    el.className = 'step';
    if (overview.x !== undefined) el.setAttribute('data-x', String(overview.x));
    if (overview.y !== undefined) el.setAttribute('data-y', String(overview.y));
    if (overview.z !== undefined) el.setAttribute('data-z', String(overview.z));
    if (overview.scale !== undefined) el.setAttribute('data-scale', String(overview.scale));
    container.appendChild(el);
  }
}

// Module scripts are deferred — DOM is ready and impress.js (regular script) already executed.
buildSlides();
(window as any).impress().init();
"""


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
    - Sets up JSON-based module loading: removes inline ``impress().init()``, ensures
      ``impress.js`` regular script and ``main.ts`` module script are present.
    - Replaces ``main_ts`` with a stable JSON-loader template so slides are rendered
      from ``slides.json`` rather than hardcoded in HTML.
    """
    clean_html = strip_external_links_from_html(artifacts.index_html)
    clean_html = ensure_impress_json_module_setup(clean_html)
    clean_css = strip_external_imports_from_css(artifacts.style_css)
    clean_css = strip_conflicting_vazirmatn_face_from_css(clean_css)
    font_css = build_local_font_css(font_file_name, font_family, variable_font, font_format)

    return SlideDeckArtifacts(
        spatial_mapping=artifacts.spatial_mapping,
        index_html=clean_html.strip(),
        style_css=(font_css + "\n\n" + clean_css.strip()).strip(),
        main_ts=build_stable_impress_main_ts_json_loader().strip(),
        slides_json=artifacts.slides_json,
    )


def build_stable_slide_main_ts() -> str:
        return """import slidesData from './slides.json';

interface SlideEntry {
    id?: string;
    x?: number;
    y?: number;
    scale?: number;
    html: string;
}

interface SlidesData {
    slides: SlideEntry[];
}

function buildSlides(): void {
    const world =
        document.getElementById('world') ??
        document.getElementById('camera') ??
        document.querySelector<HTMLElement>('#viewport > div');

    if (!world) return;

    (slidesData as unknown as SlidesData).slides.forEach((slide, idx) => {
        const el = document.createElement('div');
        el.className = 'slide';
        if (slide.id) el.id = slide.id;
        el.dataset.x = String(slide.x ?? idx * 1100);
        el.dataset.y = String(slide.y ?? 0);
        el.dataset.scale = String(slide.scale ?? 1);
        el.innerHTML = slide.html;
        world.appendChild(el);
    });
}

interface SlideData {
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

    private init(): void {
        this.slides = Array.from(
            this.world.querySelectorAll<HTMLElement>('.slide')
        ).map((el) => ({
            x: parseFloat(el.dataset.x ?? '0'),
            y: parseFloat(el.dataset.y ?? '0'),
            scale: parseFloat(el.dataset.scale ?? '1'),
            el,
        }));

        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') {
                e.preventDefault();
                this.next();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                this.prev();
            }
        });

        let touchStartX = 0;
        let touchStartY = 0;
        window.addEventListener('touchstart', (e) => {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
        });
        window.addEventListener('touchend', (e) => {
            const deltaX = e.changedTouches[0].clientX - touchStartX;
            const deltaY = e.changedTouches[0].clientY - touchStartY;
            const delta = Math.abs(deltaX) > Math.abs(deltaY) ? deltaX : deltaY;
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
            slide.el.classList.toggle('active', index === this.currentIndex);
            slide.el.classList.toggle('prev', index < this.currentIndex);
            slide.el.classList.toggle('next', index > this.currentIndex);
        });

        if (this.progressEl) {
            const pct = this.slides.length > 1
                ? (this.currentIndex / (this.slides.length - 1)) * 100
                : 0;
            this.progressEl.style.width = `${pct}%`;
        }
    }
}

window.addEventListener('DOMContentLoaded', () => {
    buildSlides();
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

#world,
#camera {{
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    transform-origin: 0 0;
    will-change: transform;
}}

.slide {{
    position: absolute;
    box-sizing: border-box;
    max-width: min(var(--versline-slide-max-width), calc(100vw - var(--versline-slide-gutter-x))) !important;
{slide_height_line}
    padding: 2rem;
    background: var(--slide-bg, #fff);
    border-radius: 8px;
    box-shadow: 0 4px 24px rgba(0,0,0,.15);
{slide_overflow_lines}
}}

#progress {{
    position: fixed;
    bottom: 0;
    left: 0;
    height: 4px;
    width: 0%;
    background: var(--accent-color, #0066cc);
    transition: width 0.4s ease;
    z-index: 9999;
}}

#controls {{
    position: fixed;
    bottom: 1.5rem;
    right: 1.5rem;
    display: flex;
    gap: 0.5rem;
    z-index: 9999;
}}

#controls button {{
    padding: 0.4rem 0.9rem;
    font-size: 1rem;
    background: rgba(0,0,0,.55);
    color: #fff;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}}

#controls button:hover {{
    background: rgba(0,0,0,.8);
}}
"""


def apply_slide_js_bundle(
    artifacts: SlideDeckArtifacts,
    font_file_name: str,
    font_family: str,
    variable_font: bool,
    font_format: str,
    no_scroll: bool = True,
    uniform_size: bool = True,
    slide_size: str = "medium",
) -> SlideDeckArtifacts:
    """Post-process artifacts for standard (non-Impress.js) presentation mode.

    - Strips external CDN links/imports (keeps local asset references intact).
    - Injects local @font-face and broad font-family rule.
    - Appends responsive layout CSS overrides.
    - Injects the stable slide main.ts (reads slides.json, handles navigation).
    """
    clean_html = strip_external_links_from_html(artifacts.index_html)
    clean_css = strip_external_imports_from_css(artifacts.style_css)
    clean_css = strip_conflicting_vazirmatn_face_from_css(clean_css)
    font_css = build_local_font_css(font_file_name, font_family, variable_font, font_format)
    overrides = build_responsive_slide_overrides_css(no_scroll, uniform_size, slide_size).strip()

    return SlideDeckArtifacts(
        spatial_mapping=artifacts.spatial_mapping,
        index_html=clean_html.strip(),
        style_css=(font_css + "\n\n" + clean_css.strip() + "\n\n" + overrides).strip(),
        main_ts=build_stable_slide_main_ts().strip(),
        slides_json=artifacts.slides_json,
    )


def find_last_slide_position(html_content: str) -> tuple[int, int]:
    """Return ``(last_x, last_y)`` by scanning ``data-x`` / ``data-y`` attributes."""
    x_vals = [int(v) for v in re.findall(r'data-x=["\'](-?\d+)["\']', html_content)]
    y_vals = [int(v) for v in re.findall(r'data-y=["\'](-?\d+)["\']', html_content)]
    last_x = max(x_vals) if x_vals else 0
    last_y = y_vals[-1] if y_vals else 0
    return last_x, last_y


def extract_new_slides_html(raw_response: str) -> str:
    """Parse the LLM response for HTML chunk mode and return the HTML snippet."""
    cleaned = _strip_outer_code_fence(raw_response)

    payload = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            payload = parsed
    except json.JSONDecodeError:
        payload = _try_parse_first_json_object(cleaned)

    if payload:
        # If the add prompt returned new_slides_json (JSON mode), there is no HTML to inject.
        if payload.get("new_slides_json") is not None:
            return ""

        value = (
            payload.get("new_slides_html")
            or payload.get("slides_html")
            or payload.get("html")
        )
        if isinstance(value, str):
            return value.strip()

    html_blocks = re.findall(r"```html\n(.*?)```", raw_response, re.DOTALL)
    if html_blocks:
        return html_blocks[0].strip()

    return cleaned if cleaned.lstrip().startswith("<") else ""


def extract_new_slides_json(raw_response: str) -> list:
    """Parse the LLM response for JSON-based chunk mode and return the new slides array."""
    cleaned = _strip_outer_code_fence(raw_response)
    payload = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            payload = parsed
        elif isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        payload = _try_parse_first_json_object(cleaned)

    if payload:
        value = payload.get("new_slides_json") or payload.get("new_slides")
        if isinstance(value, list):
            return value

    # Fallback: try to find a bare JSON array in the response
    try:
        idx = cleaned.find("[")
        if idx >= 0:
            arr = json.loads(cleaned[idx:])
            if isinstance(arr, list):
                return arr
    except Exception:  # noqa: BLE001
        pass

    return []


def find_last_slide_position_from_json(slides_json: str) -> tuple[int, int]:
    """Return ``(last_x, last_y)`` coordinates from a ``slides.json`` string."""
    try:
        data = json.loads(slides_json)
        slides = data.get("slides", [])
        x_vals = [int(s["x"]) for s in slides if isinstance(s.get("x"), (int, float))]
        y_vals = [int(s["y"]) for s in slides if isinstance(s.get("y"), (int, float))]
        return (max(x_vals) if x_vals else 0, y_vals[-1] if y_vals else 0)
    except Exception:  # noqa: BLE001
        return (0, 0)


def append_slides_to_json(existing_json: str, new_slides: list) -> str:
    """Append *new_slides* objects to the ``slides`` array in a ``slides.json`` string."""
    try:
        data = json.loads(existing_json)
        data.setdefault("slides", []).extend(new_slides)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        return existing_json


class SlideGenerationService:
    def __init__(
        self,
        model: Optional[str] = None,
        impress: bool = False,
        no_scroll: bool = True,
        uniform_size: bool = True,
        slide_size: str = "medium",
        progress_callback=None,
    ):
        self.model = model or settings.llm.model
        self.impress = impress
        self.no_scroll = no_scroll
        self.uniform_size = uniform_size
        self.slide_size = slide_size
        self._progress_callback = progress_callback

    def _request_generation(self, prompt: str) -> str:
        client = ai.configure_openai(
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    def _render_prompt(self, markdown_content: str) -> str:
        prompt_file = "slides_impress_prompt.md" if self.impress else "slides_prompt.md"
        template = load_prompt(prompt_file)
        return template.replace("{{markdown_content}}", markdown_content)

    def _render_add_prompt(
        self,
        markdown_chunk: str,
        style_css: str,
        last_x: int,
        last_y: int,
    ) -> str:
        add_prompt_file = (
            "slides_impress_add_prompt.md" if self.impress else "slides_add_prompt.md"
        )
        template = load_prompt(add_prompt_file)
        return (
            template
            .replace("{{markdown_content}}", markdown_chunk)
            .replace("{{style_css}}", style_css)
            .replace("{{last_x}}", str(last_x))
            .replace("{{last_y}}", str(last_y))
        )

    def generate(
        self,
        markdown_content: str,
        output_dir: str,
        font_file_name: str = "Vazirmatn[wght].woff2",
        font_family: str = DEFAULT_SLIDES_FONT_FAMILY,
        variable_font: bool = True,
        font_format: str = DEFAULT_SLIDES_FONT_FORMAT,
        chunk_size: int = 3000,
        progress_callback=None,
    ) -> dict:
        _progress = progress_callback or self._progress_callback or (lambda msg: None)

        deck_dir = Path(output_dir)
        deck_dir.mkdir(parents=True, exist_ok=True)

        chunks = _split_markdown(markdown_content, chunk_size)
        if not chunks:
            raise ValueError("No content to generate slides from.")

        logger.info(f"Generating slides from {len(chunks)} chunk(s)...")

        # --- First chunk: full generation ---
        _progress(f"Calling LLM for chunk 1/{len(chunks)}…")
        raw_first = self._request_generation(self._render_prompt(chunks[0]))
        _progress(f"Parsing response for chunk 1/{len(chunks)}…")
        artifacts = extract_slide_artifacts(raw_first)
        if not artifacts:
            raise ValueError(
                f"Failed to extract slide artifacts from LLM response.\n"
                f"Raw response (first 500 chars): {raw_first[:500]}"
            )

        if self.impress:
            artifacts = apply_impress_js_bundle(
                artifacts,
                font_file_name=font_file_name,
                font_family=font_family,
                variable_font=variable_font,
                font_format=font_format,
            )
        else:
            artifacts = apply_slide_js_bundle(
                artifacts,
                no_scroll=self.no_scroll,
                uniform_size=self.uniform_size,
                slide_size=self.slide_size,
                font_file_name=font_file_name,
                font_family=font_family,
                variable_font=variable_font,
                font_format=font_format,
            )

        # --- Subsequent chunks: append slides only ---
        for chunk_idx, chunk in enumerate(chunks[1:], start=2):
            logger.info(f"Processing chunk {chunk_idx}/{len(chunks)}: adding slides...")

            if artifacts.slides_json:
                # JSON mode: append new slides to the JSON array
                last_x, last_y = find_last_slide_position_from_json(artifacts.slides_json)
                new_slides = self._generate_add_slides_json_request(
                    markdown_chunk=chunk,
                    style_css=artifacts.style_css,
                    last_x=last_x,
                    last_y=last_y,
                )
                updated_json = append_slides_to_json(artifacts.slides_json, new_slides)
                artifacts = SlideDeckArtifacts(
                    spatial_mapping=artifacts.spatial_mapping,
                    index_html=artifacts.index_html,
                    style_css=artifacts.style_css,
                    main_ts=artifacts.main_ts,
                    slides_json=updated_json,
                )
            else:
                # HTML injection fallback mode
                _progress(f"Calling LLM for chunk {chunk_idx}/{len(chunks)}…")
                last_x, last_y = find_last_slide_position(artifacts.index_html)
                new_slides_html = self._generate_add_slides_request(
                    markdown_chunk=chunk,
                    style_css=artifacts.style_css,
                    last_x=last_x,
                    last_y=last_y,
                )
                _progress(f"Merging slides from chunk {chunk_idx}/{len(chunks)}…")
                updated_html = inject_slides_into_deck(artifacts.index_html, new_slides_html)
                artifacts = SlideDeckArtifacts(
                    spatial_mapping=artifacts.spatial_mapping,
                    index_html=updated_html,
                    style_css=artifacts.style_css,
                    main_ts=artifacts.main_ts,
                    slides_json=artifacts.slides_json,
                )

        _progress("Writing output files…")
        index_path = deck_dir / "index.html"
        style_path = deck_dir / "style.css"
        main_path = deck_dir / "main.ts"
        mapping_path = deck_dir / "spatial-mapping.md"

        index_path.write_text(artifacts.index_html + "\n", encoding="utf-8")
        style_path.write_text(artifacts.style_css + "\n", encoding="utf-8")
        main_path.write_text(artifacts.main_ts + "\n", encoding="utf-8")
        mapping_path.write_text((artifacts.spatial_mapping or "No mapping summary provided.") + "\n", encoding="utf-8")

        result: dict = {
            "deck_dir": str(deck_dir),
            "index_html": str(index_path),
            "style_css": str(style_path),
            "main_ts": str(main_path),
            "spatial_mapping": str(mapping_path),
        }

        if artifacts.slides_json:
            slides_json_path = deck_dir / "slides.json"
            slides_json_path.write_text(artifacts.slides_json + "\n", encoding="utf-8")
            result["slides_json"] = str(slides_json_path)

        # Copy font file into the deck directory if it exists
        font_src = DEFAULT_SLIDES_FONT_PATH if font_file_name == DEFAULT_SLIDES_FONT_PATH.name else Path(font_file_name)
        if font_src.exists():
            font_dest = deck_dir / font_src.name
            if not font_dest.exists():
                shutil.copy2(font_src, font_dest)

        return result

    def _generate_add_slides_request(
        self,
        markdown_chunk: str,
        style_css: str,
        last_x: int,
        last_y: int,
    ) -> str:
        """Request the LLM to generate additional slides as HTML."""
        prompt = self._render_add_prompt(markdown_chunk, style_css, last_x, last_y)
        raw = self._request_generation(prompt)
        return extract_new_slides_html(raw)

    def _generate_add_slides_json_request(
        self,
        markdown_chunk: str,
        style_css: str,
        last_x: int,
        last_y: int,
    ) -> list:
        """Like ``_generate_add_slides_request`` but returns a list of slide dicts."""
        prompt = self._render_add_prompt(markdown_chunk, style_css, last_x, last_y)
        raw = self._request_generation(prompt)
        return extract_new_slides_json(raw)


def _split_markdown(content: str, chunk_size: int) -> list[str]:
    """Split *content* into chunks of at most *chunk_size* characters.

    Splits prefer heading boundaries (``# ``) to keep related content together.
    If no heading boundary is found within range, a hard split is used.
    """
    if len(content) <= chunk_size:
        return [content]

    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        if end >= len(content):
            chunks.append(content[start:])
            break

        split_pos = content.rfind("\n# ", start, end)
        if split_pos == -1 or split_pos <= start:
            split_pos = content.rfind("\n", start, end)
        if split_pos == -1 or split_pos <= start:
            split_pos = end

        chunks.append(content[start:split_pos])
        start = split_pos

    return [c for c in chunks if c.strip()]
