import json
import tempfile
import unittest
from pathlib import Path

from versline.services.slides import (
    SlideDeckArtifacts,
    apply_local_font_bundle,
    apply_runtime_and_responsive_defaults,
    extract_slide_artifacts,
    write_vite_project_files,
)


class TestSlidesService(unittest.TestCase):
    def test_extract_slide_artifacts_from_json(self):
        raw = """
```json
{
  "spatial_mapping": "H1 hubs on x axis, H2 clustered nearby with higher z and lower scale.",
  "index_html": "<html><body>ok</body></html>",
  "style_css": "body { color: #eee; }",
  "main_ts": "console.log('ok');"
}
```
"""
        artifacts = extract_slide_artifacts(raw)

        self.assertIn("H1 hubs", artifacts.spatial_mapping)
        self.assertIn("<html>", artifacts.index_html)
        self.assertIn("color", artifacts.style_css)
        self.assertIn("console.log", artifacts.main_ts)

    def test_extract_slide_artifacts_from_code_fences(self):
        raw = """
Spatial strategy: H1 are anchors, H2 are radial child nodes.

```html
<html><body><section>Slide</section></body></html>
```

```css
section { opacity: 1; }
```

```ts
const ready: boolean = true;
```
"""
        artifacts = extract_slide_artifacts(raw)

        self.assertIn("H1", artifacts.spatial_mapping)
        self.assertIn("section", artifacts.index_html)
        self.assertIn("opacity", artifacts.style_css)
        self.assertIn("boolean", artifacts.main_ts)

    def test_write_vite_project_files_with_single_file_plugin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            write_vite_project_files(project_dir, single_file=True)

            package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
            dev_deps = package_json.get("devDependencies", {})
            self.assertIn("vite", dev_deps)
            self.assertIn("typescript", dev_deps)
            self.assertIn("vite-plugin-singlefile", dev_deps)

            vite_config = (project_dir / "vite.config.ts").read_text(encoding="utf-8")
            self.assertIn("viteSingleFile()", vite_config)

    def test_write_vite_project_files_without_single_file_plugin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            write_vite_project_files(project_dir, single_file=False)

            package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
            dev_deps = package_json.get("devDependencies", {})
            self.assertIn("vite", dev_deps)
            self.assertNotIn("vite-plugin-singlefile", dev_deps)

            vite_config = (project_dir / "vite.config.ts").read_text(encoding="utf-8")
            self.assertNotIn("viteSingleFile()", vite_config)

    def test_apply_local_font_bundle_strips_external_and_injects_font_face(self):
        artifacts = SlideDeckArtifacts(
            spatial_mapping="map",
            index_html="""
<html><head>
<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/reveal.js/dist/reveal.css'>
<script src='https://cdn.jsdelivr.net/npm/reveal.js/dist/reveal.js'></script>
</head><body><h1>deck</h1><script src='main.ts'></script></body></html>
""",
            style_css="""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
body { margin: 0; }
""",
            main_ts="console.log('ok');",
        )

        bundled = apply_local_font_bundle(
            artifacts=artifacts,
            font_file_name="Vazirmatn[wght].ttf",
            font_family="Vazirmatn",
            variable_font=True,
            font_format="truetype",
        )

        self.assertNotIn("cdn.jsdelivr.net", bundled.index_html)
        self.assertIn('type="module"', bundled.index_html)
        self.assertIn('src="main.ts"', bundled.index_html)
        self.assertNotIn("fonts.googleapis.com", bundled.style_css)
        self.assertIn("@font-face", bundled.style_css)
        self.assertIn("font-weight: 100 900", bundled.style_css)
        self.assertIn("Vazirmatn[wght].ttf", bundled.style_css)

    def test_runtime_and_responsive_defaults_enforced(self):
        artifacts = SlideDeckArtifacts(
            spatial_mapping="map",
            index_html="<html><body><div id='world'></div></body></html>",
            style_css=".slide { width: 900px; height: 600px; }",
            main_ts="console.log('raw runtime');",
        )

        normalized = apply_runtime_and_responsive_defaults(artifacts)

        self.assertIn("scale(${finalScale}) translate3d(${x}px, ${y}px, 0px)", normalized.main_ts)
        self.assertIn("const correctionX = viewportCenterX - activeCenterX;", normalized.main_ts)
        self.assertIn("translate3d(${correctionX}px, ${correctionY}px, 0px)", normalized.main_ts)
        self.assertIn("const x = -current.x;", normalized.main_ts)
        self.assertIn("const fitScale = Math.min", normalized.main_ts)
        self.assertIn("document.getElementById('camera')", normalized.main_ts)
        self.assertIn("document.getElementById('next')", normalized.main_ts)
        self.assertIn("document.getElementById('prev')", normalized.main_ts)
        self.assertIn("--versline-slide-max-width", normalized.style_css)
        self.assertIn("height: 100vh !important", normalized.style_css)
        self.assertIn("top: 0 !important", normalized.style_css)
        self.assertIn("transition: none !important", normalized.style_css)
        self.assertIn("margin-left: 0 !important", normalized.style_css)
        self.assertIn(".slide.active", normalized.style_css)
        self.assertIn("@media (max-width: 600px)", normalized.style_css)


if __name__ == "__main__":
    unittest.main()
