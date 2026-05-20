import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from versline.services.slides import (
    IMPRESS_JS_ASSET_PATH,
    SlideDeckArtifacts,
    apply_impress_js_bundle,
    apply_local_font_bundle,
    apply_runtime_and_responsive_defaults,
    ensure_impress_script_tags,
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


class TestEnsureImpressScriptTags(unittest.TestCase):
    def test_already_complete_unchanged(self):
        html = (
            "<html><body>"
            '<script src="impress.min.js"></script>'
            "<script>impress().init();</script>"
            "</body></html>"
        )
        result = ensure_impress_script_tags(html)
        self.assertEqual(result.count('src="impress.min.js"'), 1)
        self.assertEqual(result.count("impress().init()"), 1)

    def test_injects_both_when_missing(self):
        html = "<html><body><div id='impress'></div></body></html>"
        result = ensure_impress_script_tags(html)
        self.assertIn('src="impress.min.js"', result)
        self.assertIn("impress().init();", result)
        self.assertIn("</body>", result)
        impress_js_pos = result.index('src="impress.min.js"')
        body_close_pos = result.index("</body>")
        self.assertLess(impress_js_pos, body_close_pos)

    def test_injects_only_missing_src(self):
        html = "<html><body><script>impress().init();</script></body></html>"
        result = ensure_impress_script_tags(html)
        self.assertIn('src="impress.min.js"', result)
        self.assertEqual(result.count("impress().init()"), 1)

    def test_injects_only_missing_init(self):
        html = '<html><body><script src="impress.min.js"></script></body></html>'
        result = ensure_impress_script_tags(html)
        self.assertIn("impress().init();", result)
        self.assertEqual(result.count('src="impress.min.js"'), 1)

    def test_appends_at_end_when_no_body_tag(self):
        html = "<div id='impress'><div class='step slide' data-x='0' data-y='0'>Slide</div></div>"
        result = ensure_impress_script_tags(html)
        self.assertIn('src="impress.min.js"', result)
        self.assertIn("impress().init();", result)

    def test_empty_input_returns_empty(self):
        self.assertEqual(ensure_impress_script_tags(""), "")
        self.assertEqual(ensure_impress_script_tags("   "), "   ")


class TestApplyImpressJsBundle(unittest.TestCase):
    def _make_artifacts(self, html="", css="", main_ts="// Navigation is handled by impress.js"):
        return SlideDeckArtifacts(
            spatial_mapping="test",
            index_html=html or (
                "<html><head>"
                "<link rel='stylesheet' href='https://cdn.example.com/reset.css'>"
                "<script src='https://cdn.example.com/lib.js'></script>"
                "</head>"
                "<body>"
                "<div id='impress'>"
                "<div class='step slide' data-x='0' data-y='0'>Slide 1</div>"
                "</div>"
                "</body></html>"
            ),
            style_css=css or "@import url('https://fonts.googleapis.com/css2?family=Inter&display=swap');\nbody { margin: 0; }",
            main_ts=main_ts,
        )

    def test_strips_external_cdn_links(self):
        artifacts = self._make_artifacts()
        result = apply_impress_js_bundle(
            artifacts, "Vazirmatn[wght].ttf", "Vazirmatn", True, "truetype"
        )
        self.assertNotIn("cdn.example.com", result.index_html)
        self.assertNotIn("fonts.googleapis.com", result.style_css)

    def test_injects_font_face(self):
        artifacts = self._make_artifacts()
        result = apply_impress_js_bundle(
            artifacts, "Vazirmatn[wght].ttf", "Vazirmatn", True, "truetype"
        )
        self.assertIn("@font-face", result.style_css)
        self.assertIn("Vazirmatn[wght].ttf", result.style_css)
        self.assertIn("font-weight: 100 900", result.style_css)

    def test_ensures_impress_script_tags_in_html(self):
        artifacts = self._make_artifacts()
        result = apply_impress_js_bundle(
            artifacts, "Vazirmatn[wght].ttf", "Vazirmatn", True, "truetype"
        )
        self.assertIn('src="impress.min.js"', result.index_html)
        self.assertIn("impress().init();", result.index_html)

    def test_preserves_main_ts_placeholder(self):
        placeholder = "// Navigation is handled by impress.js"
        artifacts = self._make_artifacts(main_ts=placeholder)
        result = apply_impress_js_bundle(
            artifacts, "Vazirmatn[wght].ttf", "Vazirmatn", True, "truetype"
        )
        self.assertEqual(result.main_ts, placeholder)

    def test_does_not_inject_module_type_on_impress_scripts(self):
        """impress.min.js script must not become type=module."""
        artifacts = self._make_artifacts()
        result = apply_impress_js_bundle(
            artifacts, "Vazirmatn[wght].ttf", "Vazirmatn", True, "truetype"
        )
        self.assertNotIn('type="module"', result.index_html)


class TestEnsureImpressAssetCached(unittest.TestCase):
    def test_returns_existing_asset_without_download(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_asset = Path(tmpdir) / "impress.min.js"
            fake_asset.write_bytes(b"/* impress.js stub */")

            with patch("versline.services.slides.IMPRESS_JS_ASSET_PATH", fake_asset):
                from versline.services.slides import _ensure_impress_js_asset
                path = _ensure_impress_js_asset()
                self.assertEqual(path, fake_asset)


class TestGeneratorImpressPromptLoading(unittest.TestCase):
    def test_use_impress_loads_impress_prompt(self):
        from versline.services.slides import MarkdownSlideDeckGenerator
        gen = MarkdownSlideDeckGenerator(
            provider="Google",
            model="gemini-1.5-flash",
            api_key="fake",
            use_impress=True,
        )
        self.assertIn("Impress.js", gen.prompt_template)
        self.assertIn("data-x", gen.prompt_template)

    def test_use_impress_false_loads_standard_prompt(self):
        from versline.services.slides import MarkdownSlideDeckGenerator
        gen = MarkdownSlideDeckGenerator(
            provider="Google",
            model="gemini-1.5-flash",
            api_key="fake",
            use_impress=False,
        )
        self.assertNotIn("impress.js", gen.prompt_template.lower()[:200])

    def test_use_impress_loads_impress_add_prompt(self):
        from versline.services.slides import MarkdownSlideDeckGenerator
        gen = MarkdownSlideDeckGenerator(
            provider="Google",
            model="gemini-1.5-flash",
            api_key="fake",
            use_impress=True,
        )
        self.assertIn("step slide", gen.add_prompt_template)
        self.assertIn("data-x", gen.add_prompt_template)


if __name__ == "__main__":
    unittest.main()
