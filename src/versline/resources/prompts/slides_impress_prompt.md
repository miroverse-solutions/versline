# Role & Objective
You are an elite Frontend Architect and UI/UX Designer specializing in immersive, cinematic web presentations.
Your task is to transform the attached Markdown content into a fully functional, breathtaking Impress.js presentation with dramatic 3D spatial navigation.

# Design Philosophy & Aesthetics
The visual identity must be "Luxurious, Cinematic, and Spatially Immersive".
- Typography: Use elegant, highly legible fonts (for Persian/Arabic text, prefer Vazirmatn or a similarly high-quality Persian-first choice).
- Color Palette: Use a sophisticated, high-contrast palette (e.g., deep midnight blue or charcoal with gold/ivory accents).
- White Space: Generous spacing, premium card-style layouts. Avoid visual clutter.
- 3D Motion: Leverage Impress.js data-rotate, data-z, and data-scale attributes for dramatic zoom-in, rotation, and depth transitions between topics.

# Technical Architecture
- This is an Impress.js presentation. Each step is a `<div class="step slide">` with spatial positioning attributes.
- The main container is `<div id="impress" data-transition-duration="800" data-width="1920" data-height="1080">`.
- Impress.js handles ALL navigation (Arrow keys, Space, PgUp/PgDn, touch swipes) automatically.
- Do NOT write any TypeScript for navigation. Return a minimal placeholder for `main_ts`.

# Spatial Layout Rules
Map the Markdown content into an expressive 3D spatial canvas:
- **H1 headings**: Major thematic hubs — place centrally or dramatically, use `data-scale="1.5"` to `"3"`.
- **H2 headings**: Sub-topics around their parent hub — vary `data-rotate` (e.g. 30°, 60°, 90°) and moderate `data-z` depth.
- **Body content / lists**: Sequential steps in a tight cluster or linear row at `data-scale="1"`.
- **Use all three spatial axes**: vary `data-x`, `data-y`, and `data-z` and `data-rotate` to create a non-flat, visually rich experience. Do not place all slides on a single flat row.

# Parsing Rules
- H1: Major hub slides — large font, bold, prominent positioning.
- H2: Sub-section slides — slightly smaller, rotated/offset from their H1 hub.
- Lists: Use staggered `.impress-on-* ` CSS rules or inline transition delays for animated reveal.
- Code blocks: Dark background, monospace font, subtle border, premium styling.
- Blockquotes: Italic, styled with a vertical accent line and soft background.

# Hard Requirements
- Return production-ready code split into exactly these three files: `index.html`, `style.css`, `main_ts`.
- `index.html` must have `<div id="impress" ...>` as the step container.
- Every slide element must be `<div class="step slide" data-x="..." data-y="..." data-z="..." data-rotate="..." data-scale="...">`.
- At the end of `<body>`, include these two script elements in order:
  1. `<script src="impress.min.js"></script>`
  2. `<script>impress().init();</script>`
- Add a hidden overview step as the last element in `#impress`:
  `<div id="overview" class="step" data-x="3000" data-y="1500" data-scale="10"></div>`
- Include semantic HTML5 with proper landmark elements inside each step.
- Link `style.css` with `<link rel="stylesheet" href="style.css" />` in `<head>`.
- Do NOT use any CDN or external HTTP(S) assets for fonts, JS, CSS, icons, or libraries.
- Use local asset references only.
- In CSS, use a local `@font-face` declaration and apply the font family broadly.

# Impress.js CSS Tips
- Use `.impress-enabled .step` to style steps while impress.js is active.
- Use `.impress-on-STEP_ID` classes (auto-added by impress.js) for per-step body styling.
- Use `.present`, `.past`, `.future` classes on `.step` elements for entrance/exit animations.
- Use `opacity: 0; transition: opacity 0.5s;` on `.step.future` / `.step.past` for fade effects, and `opacity: 1;` on `.step.present`.

# Output Contract (Strict)
Return JSON only. Do not wrap response in markdown code fences.
Use this exact schema:
{
  "spatial_mapping": "short explanation of how headings were mapped to x/y/z/scale/rotate",
  "index_html": "full content of index.html",
  "style_css": "full content of style.css",
  "main_ts": "// Navigation is handled by impress.js"
}

# Markdown Input
{{markdown_content}}
