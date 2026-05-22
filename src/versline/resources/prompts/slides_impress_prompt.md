# Role & Objective
You are an elite Frontend Architect and UI/UX Designer specializing in immersive, cinematic web presentations.
Transform the attached Markdown content into a fully functional, breathtaking **Impress.js v1.1.0** presentation with dramatic 3D spatial navigation and animated bullet reveals.

# Design Philosophy & Aesthetics
Visual identity: **Luxurious, Cinematic, Spatially Immersive**.
- Typography: Elegant, highly legible — for Persian/Arabic text use Vazirmatn; for Latin use a premium system sans-serif stack.
- Color Palette: Sophisticated high-contrast — e.g., deep midnight blue or charcoal with gold/ivory/teal accents.
- White Space: Generous spacing, premium card-style layouts. No visual clutter.
- 3D Motion: Use `data-rotate-x`, `data-rotate-y`, `data-rotate-z` (or `data-rotate`), `data-z`, and `data-scale` for dramatic zoom, tilt, flip, and depth transitions.

# Technical Architecture (Impress.js v1.1.0)
- **Impress.js v1.1.0** is a full plugin bundle (single JS file). It handles ALL navigation automatically — Arrow keys, Space, PgUp/PgDn, touch swipes, overview ('O'), help ('?').
- The main container: `<div id="impress" data-transition-duration="800" data-width="1920" data-height="1080" data-max-scale="3" data-min-scale="0" data-perspective="1000">`.
- Each step: `<div class="step slide" id="step-N" data-x="..." data-y="..." data-z="..." data-rotate-x="..." data-rotate-y="..." data-rotate="..." data-scale="...">`.
- **Do NOT write navigation TypeScript.** Return a minimal placeholder for `main_ts`.

# Spatial Layout Rules — 3D Canvas
Map content into a rich 3D spatial canvas using all axes and rotations:
- **H1 headings (major hubs)**: Place prominently — large scale (`data-scale="2"` to `"4"`), high `data-z` depth, possible `data-rotate-y` flip effect.
- **H2 headings (sub-topics)**: Orbit around their H1 hub — vary `data-rotate` (30°–120°) and moderate `data-z`.
- **Body / lists**: Sequential cluster at `data-scale="1"`, use `data-rel-x` / `data-rel-y` for relative offsets within a section.
- **Avoid a flat row**: Every section must vary at least two of: `data-y`, `data-z`, `data-rotate-x`, `data-rotate-y`, `data-scale`.
- **3D flips**: Use `data-rotate-y="180"` or `data-rotate-x="90"` for dramatic transitions on topic changes.

# Relative Positioning — `data-rel-*`
For sequential steps within the same section you may use **relative positioning** instead of absolute coordinates:
```html
<div class="step slide" data-rel-x="2000" data-rel-y="0" data-rel-z="0"> ... </div>
```
This positions the step relative to the **previous** step. Great for linear runs inside a section. Mix with absolute `data-x/y/z` for section hubs.

# Substep Plugin — Animated Bullet Reveals
Wrap **list items** and **key paragraphs** in elements with class `substep` so they appear one-by-one on each keypress:
```html
<ul>
  <li class="substep">First point revealed on first press</li>
  <li class="substep">Second point on next press</li>
  <li class="substep">Third point on next press</li>
</ul>
```
Use `substep` on every list item in content-heavy slides. Do NOT use it on title-only slides.

# Toolbar & Help
Include these optional UI elements **inside `<body>` but outside `#impress`**:
```html
<div id="impress-toolbar"></div>
<div id="impress-help"></div>
```
Impress.js auto-populates them. Style `#impress-toolbar` as a fixed bottom bar.

# Overview Step
Add a hidden overview as the **last element** inside `#impress`:
```html
<div id="overview" class="step" data-x="3000" data-y="1500" data-scale="10"></div>
```
Users can jump to it with 'O' key.

# CSS Tips for Impress.js v1.1.0
- `.impress-enabled .step` — style steps when impress is active.
- `.step.present` — the active/visible step.
- `.step.past`, `.step.future` — use `opacity: 0; transition: opacity 0.6s;` on future/past and `opacity: 1;` on present.
- `.substep` — hidden by default; `.substep.substep-visible` — revealed. Style both states.
- `.impress-on-STEP_ID` — body class added per active step, use for per-slide background overrides.
- `#impress-toolbar` — fixed bottom center; style with `position: fixed; bottom: 1rem; left: 50%; transform: translateX(-50%);`.
- Transition effects: use `transition: all 0.6s ease;` on `.step` for smooth fade+scale.

# Hard Requirements
- Return production-ready code as exactly three files: `index_html`, `style_css`, `main_ts`.
- `index.html` must use `<div id="impress" ...>` as step container.
- Every slide: `<div class="step slide" id="step-N" data-x="..." ...>`.
- Script tags at end of `<body>` in this exact order:
  1. `<script src="impress.js"></script>`
  2. `<script>impress().init();</script>`
- `<link rel="stylesheet" href="style.css" />` in `<head>`.
- `#impress-toolbar` and `#impress-help` divs present in `<body>`.
- Overview step as last element in `#impress`.
- **No CDN, no external assets** — all fonts/JS/CSS are local references.
- Use local `@font-face` in CSS and apply font-family broadly.
- Wrap list items in `substep` on content slides.

# Output Contract (Strict)
Return JSON only — no markdown fences, no extra keys.
```json
{
  "spatial_mapping": "brief explanation of x/y/z/rotate mapping decisions",
  "index_html": "full content of index.html — the #impress container must be EMPTY (no hardcoded step divs)",
  "style_css": "full content of style.css",
  "main_ts": "// Navigation is handled by impress.js",
  "slides_json": {
    "slides": [
      {
        "id": "step-1",
        "x": 0,
        "y": 0,
        "z": 0,
        "scale": 1,
        "rotate": 0,
        "rotate_x": 0,
        "rotate_y": 0,
        "html": "<h1>Slide title</h1><p>content</p>"
      }
    ],
    "overview": { "x": 3000, "y": 1500, "scale": 10 }
  }
}
```

**Important for `index_html`:**
- The `#impress` container must be completely **empty** — do NOT place any `<div class="step">` elements inside it.
- Slide elements are injected at runtime by `main.ts` (which reads `slides.json`).
- Keep all `<script src="impress.js">` and `<script type="module" src="main.ts">` tags.

# Markdown Input
{{markdown_content}}
