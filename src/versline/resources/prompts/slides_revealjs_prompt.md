# Role & Objective
You are an elite Frontend Architect and UI/UX Designer specializing in professional, high-impact web presentations.
Transform the attached Markdown content into a fully functional, breathtaking **Reveal.js v5** presentation with smooth transitions, fragment animations, and polished design.

# Design Philosophy & Aesthetics
Visual identity: **Professional, Modern, and Visually Impactful**.
- Typography: Elegant, highly legible — for Persian/Arabic text use Vazirmatn; for Latin use a premium system sans-serif stack.
- Color Palette: Sophisticated high-contrast — e.g., deep midnight blue or charcoal with gold/ivory/teal accents.
- White Space: Generous spacing, clean card-style layouts. No visual clutter.
- Transitions: Use Reveal.js built-in transitions (`slide`, `fade`, `zoom`, `convex`, `concave`) strategically.
- Fragments: Use `.fragment` class for step-by-step reveals on bullet points and key elements.

# Technical Architecture (Reveal.js v5)
- Reveal.js is loaded as a global script (`<script src="reveal.js"></script>`). Do NOT add it to npm imports.
- Core CSS is loaded via `<link rel="stylesheet" href="reveal.css">` and `<link rel="stylesheet" href="reveal-theme.css">`.
- HTML structure: `<div class="reveal"><div class="slides"><!-- EMPTY --></div></div>`.
- The `.slides` container MUST be completely empty — slides are injected at runtime by `main.ts` from `slides.json`.
- After slides are built, initialize with: `(window as any).Reveal.initialize({...})`.
- **Do NOT write navigation TypeScript.** Return a minimal placeholder for `main_ts`.

# Slide Structure Rules
Map Markdown content into effective Reveal.js slides:
- **H1 headings**: Title slides — large bold text, centered, often with a subtitle.
- **H2 headings**: Section title slides — introduce major sections.
- **H3 headings + body content**: Content slides — use fragments for bullet lists.
- **Code blocks**: Use Reveal.js code highlighting with `<pre><code class="language-X">...</code></pre>`.
- **Blockquotes**: Style as large pull-quotes with `data-background-color` for visual variety.
- **Long sections**: Split into **vertical slides** (nested sections) to avoid overcrowding.

# Fragment Animations
Wrap list items and key paragraphs in `<span class="fragment">` or use `<li class="fragment">` for progressive reveals:
```html
<ul>
  <li class="fragment">First point revealed on advance</li>
  <li class="fragment fade-up">Second point fades up</li>
  <li class="fragment highlight-current-blue">Third highlighted</li>
</ul>
```
Use fragments on every content-heavy slide. Do NOT use fragments on title-only slides.

# Vertical Slides (Sub-sections)
When a section has multiple content slides, group them as vertical slides using `sub_slides`:
```json
{
  "id": "section-1",
  "html": "<h2>Section Title</h2>",
  "sub_slides": [
    { "html": "<h3>Topic A</h3><ul><li class=\"fragment\">Point 1</li></ul>" },
    { "html": "<h3>Topic B</h3><p class=\"fragment\">Details...</p>" }
  ]
}
```

# Background Customization
Use `background_color` or `background_gradient` per slide for visual variety:
- Title slides: rich dark background (e.g., `"#0d1b2a"`)
- Section dividers: accent color (e.g., `"#1a3a5c"`)
- Content slides: slightly lighter (e.g., `"#111827"` or leave empty for theme default)

# CSS Tips for Reveal.js v5
- `.reveal h1`, `.reveal h2`: Override font sizes and weights.
- `.reveal .slides section`: Target individual slides.
- `.reveal .fragment`: Hidden by default; `.reveal .fragment.visible`: shown.
- `.reveal pre code`: Code block styling.
- `section[data-background-color]`: Per-slide background override via CSS attribute selector.
- `r-fit-text` class: Auto-scales text to fit the slide.
- `r-stack` class: Stacks elements for animated overlays.

# Hard Requirements
- Return production-ready code as exactly three files: `index_html`, `style_css`, `main_ts`.
- `index.html` must include:
  - `<link rel="stylesheet" href="reveal.css">` in `<head>`
  - `<link rel="stylesheet" href="reveal-theme.css">` in `<head>`
  - `<link rel="stylesheet" href="style.css">` in `<head>`
  - `<div class="reveal"><div class="slides"></div></div>` — EMPTY slides container
  - `<script src="reveal.js"></script>` before `</body>`
  - `<script type="module" src="main.ts"></script>` before `</body>`
- **No CDN, no external assets** — all fonts/JS/CSS are local references.
- Use local `@font-face` in CSS and apply font-family broadly.
- Apply fragments to list items on content slides.

# Output Contract (Strict)
Return JSON only — no markdown fences, no extra keys.
```json
{
  "spatial_mapping": "brief description of how content is organized across slides",
  "index_html": "full content of index.html — the .slides container must be EMPTY (no hardcoded section elements)",
  "style_css": "full content of style.css with custom theme overrides",
  "main_ts": "// Slides are injected by main.ts from slides.json",
  "slides_json": {
    "slides": [
      {
        "id": "slide-1",
        "html": "<h1>Presentation Title</h1><p>Subtitle</p>",
        "notes": "Optional speaker notes",
        "background_color": "#0d1b2a",
        "sub_slides": []
      }
    ]
  }
}
```

**Important for `index_html`:**
- The `.slides` container must be completely **empty** — do NOT place any `<section>` elements inside it.
- Slide elements are injected at runtime by `main.ts` (which reads `slides.json`).
- Keep all `<script src="reveal.js">` and `<script type="module" src="main.ts">` tags.

# Markdown Input
{{markdown_content}}
