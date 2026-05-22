import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from versline.services.slides import (
    IMPRESS_JS_ASSET_PATH,
    SlideDeckArtifacts,
    append_slides_to_json,
    apply_impress_js_bundle,
    apply_local_font_bundle,
    apply_runtime_and_responsive_defaults,
    ensure_impress_json_module_setup,
    ensure_impress_script_tags,
    extract_new_slides_json,
    extract_slide_artifacts,
    find_last_slide_position_from_json,
    write_vite_project_files,
)


class TestSlidesService(unittest.TestCase):
    def test_extract_slide_artifacts_from_json(self):
        slides_json_obj = {"slides": [{"id": "step-1", "x": 0, "y": 0, "html": "<h1>Title</h1>"}]}
        raw = json.dumps({
            "spatial_mapping": "H1 hubs on x axis, H2 clustered nearby with higher z and lower scale.",
            "index_html": "<html><body>ok</body></html>",
            "style_css": "body { color: #eee; }",
            "main_ts": "console.log('ok');",
            "slides_json": slides_json_obj,
        })
        artifacts = extract_slide_artifacts(raw)

        self.assertIn("H1 hubs", artifacts.spatial_mapping)
        self.assertIn("<html>", artifacts.index_html)
        self.assertIn("color", artifacts.style_css)
        self.assertIn("console.log", artifacts.main_ts)
        self.assertIn("step-1", artifacts.slides_json)

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

        self.assertIn("import slidesData from './slides.json'", normalized.main_ts)
        self.assertIn("buildSlides()", normalized.main_ts)
        self.assertIn("new Presentation()", normalized.main_ts)
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
            '<script src="impress.js"></script>'
            "<script>impress().init();</script>"
            "</body></html>"
        )
        result = ensure_impress_script_tags(html)
        self.assertEqual(result.count('src="impress.js"'), 1)
        self.assertEqual(result.count("impress().init()"), 1)

    def test_injects_both_when_missing(self):
        html = "<html><body><div id='impress'></div></body></html>"
        result = ensure_impress_script_tags(html)
        self.assertIn('src="impress.js"', result)
        self.assertIn("impress().init();", result)
        self.assertIn("</body>", result)
        impress_js_pos = result.index('src="impress.js"')
        body_close_pos = result.index("</body>")
        self.assertLess(impress_js_pos, body_close_pos)

    def test_injects_only_missing_src(self):
        html = "<html><body><script>impress().init();</script></body></html>"
        result = ensure_impress_script_tags(html)
        self.assertIn('src="impress.js"', result)
        self.assertEqual(result.count("impress().init()"), 1)

    def test_injects_only_missing_init(self):
        html = '<html><body><script src="impress.js"></script></body></html>'
        result = ensure_impress_script_tags(html)
        self.assertIn("impress().init();", result)
        self.assertEqual(result.count('src="impress.js"'), 1)

    def test_appends_at_end_when_no_body_tag(self):
        html = "<div id='impress'><div class='step slide' data-x='0' data-y='0'>Slide</div></div>"
        result = ensure_impress_script_tags(html)
        self.assertIn('src="impress.js"', result)
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
        # JSON mode: impress.js as regular script + main.ts as module; no inline init()
        self.assertIn('src="impress.js"', result.index_html)
        self.assertIn('type="module"', result.index_html)
        self.assertIn('src="main.ts"', result.index_html)
        self.assertNotIn("impress().init();", result.index_html)

    def test_preserves_main_ts_json_loader(self):
        """apply_impress_js_bundle must inject the stable JSON-loader template."""
        artifacts = self._make_artifacts(main_ts="// Navigation is handled by impress.js")
        result = apply_impress_js_bundle(
            artifacts, "Vazirmatn[wght].ttf", "Vazirmatn", True, "truetype"
        )
        self.assertIn("import slidesData from './slides.json'", result.main_ts)
        self.assertIn("buildSlides()", result.main_ts)
        self.assertIn("impress().init()", result.main_ts)

    def test_does_not_inject_module_type_on_impress_script(self):
        """impress.js must be a regular (non-module) script; only main.ts is module."""
        artifacts = self._make_artifacts()
        result = apply_impress_js_bundle(
            artifacts, "Vazirmatn[wght].ttf", "Vazirmatn", True, "truetype"
        )
        # main.ts should be module
        self.assertIn('type="module" src="main.ts"', result.index_html)
        # impress.js src must not have type="module" adjacent to it
        import re
        impress_tags = re.findall(r'<script[^>]*impress[^>]*>', result.index_html)
        for tag in impress_tags:
            self.assertNotIn('type="module"', tag)


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


class TestEnsureImpressJsonModuleSetup(unittest.TestCase):
    def test_removes_inline_init(self):
        html = (
            "<html><body>"
            '<script src="impress.js"></script>'
            "<script>impress().init();</script>"
            "</body></html>"
        )
        result = ensure_impress_json_module_setup(html)
        self.assertNotIn("impress().init()", result)
        self.assertIn('src="impress.js"', result)
        self.assertIn('src="main.ts"', result)

    def test_injects_impress_and_module_scripts(self):
        html = "<html><body><div id='impress'></div></body></html>"
        result = ensure_impress_json_module_setup(html)
        self.assertIn('src="impress.js"', result)
        self.assertIn('type="module"', result)
        self.assertIn('src="main.ts"', result)

    def test_does_not_duplicate_existing_scripts(self):
        html = (
            "<html><body>"
            '<script src="impress.js"></script>'
            '<script type="module" src="main.ts"></script>'
            "</body></html>"
        )
        result = ensure_impress_json_module_setup(html)
        self.assertEqual(result.count('src="impress.js"'), 1)
        self.assertEqual(result.count('src="main.ts"'), 1)

    def test_empty_input_returns_empty(self):
        self.assertEqual(ensure_impress_json_module_setup(""), "")


class TestJsonSlideHelpers(unittest.TestCase):
    def _make_slides_json(self):
        return json.dumps({
            "slides": [
                {"id": "step-1", "x": 0, "y": 0, "html": "<h1>One</h1>"},
                {"id": "step-2", "x": 1000, "y": 0, "html": "<h2>Two</h2>"},
            ],
            "overview": {"x": 3000, "y": 1500, "scale": 10},
        })

    def test_extract_slides_json_from_payload(self):
        slides_obj = {"slides": [{"id": "step-1", "x": 0, "y": 0, "html": "<h1>Hi</h1>"}]}
        raw = json.dumps({
            "spatial_mapping": "test",
            "index_html": "<html><body></body></html>",
            "style_css": "body {}",
            "main_ts": "// ok",
            "slides_json": slides_obj,
        })
        artifacts = extract_slide_artifacts(raw)
        self.assertTrue(len(artifacts.slides_json) > 0)
        parsed = json.loads(artifacts.slides_json)
        self.assertEqual(parsed["slides"][0]["id"], "step-1")

    def test_find_last_slide_position_from_json(self):
        sj = self._make_slides_json()
        x, y = find_last_slide_position_from_json(sj)
        self.assertEqual(x, 1000)
        self.assertEqual(y, 0)

    def test_find_last_slide_position_from_empty_json(self):
        x, y = find_last_slide_position_from_json('{"slides": []}')
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)

    def test_append_slides_to_json(self):
        sj = self._make_slides_json()
        new_slides = [{"id": "step-3", "x": 2000, "y": 0, "html": "<h2>Three</h2>"}]
        result = append_slides_to_json(sj, new_slides)
        parsed = json.loads(result)
        self.assertEqual(len(parsed["slides"]), 3)
        self.assertEqual(parsed["slides"][2]["id"], "step-3")

    def test_extract_new_slides_json_from_array_payload(self):
        new_slides = [{"id": "step-3", "x": 2000, "y": 0, "html": "<h2>Three</h2>"}]
        raw = json.dumps({"new_slides_json": new_slides})
        result = extract_new_slides_json(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "step-3")

    def test_extract_new_slides_json_returns_empty_on_failure(self):
        result = extract_new_slides_json("not valid json at all")
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
