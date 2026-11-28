import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from versline.services.channel_archive import documents as docs
from versline.services.channel_archive import obsidian
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem
from versline.services.channel_archive.pipeline import ArchiveOptions, ChannelArchiver
from versline.services.channel_archive.steps import StepContext

BASE = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
STEPS = ["media", "transcribe", "documents"]


class FileSource:
    """Writes each item's source_ref (bytes) as the downloaded file, with the extension of its file name."""

    def __init__(self, posts):
        self.posts = posts
        self.downloads = []

    def resolve(self, ref):
        return ChannelInfo(ref=ref, title="کانال تست", username="testchan", channel_id=1)

    def iter_posts(self, channel, since=None, until=None, limit=None):
        yield from self.posts

    def download(self, post, item, dest_dir, stem, progress_callback=None):
        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(item.file_name).suffix if item.file_name else ".mp3"
        path = dest_dir / f"{stem}{suffix}"
        path.write_bytes(item.source_ref if isinstance(item.source_ref, bytes) else b"audio")
        self.downloads.append(path)
        return path

    def close(self):
        pass


class FakeTranscriber:
    def __init__(self):
        self.calls = []

    def process_file(self, path, **kwargs):
        self.calls.append(path)
        return f"transcript of {Path(path).stem}"


class FakeVisionLLM:
    def __init__(self):
        self.images = []

    def generate_with_image(self, prompt, image_path):
        self.images.append(Path(image_path).name)
        return "بله، حتماً، متن صفحه:\n\nمتن صفحه‌ی اسکن‌شده"


def doc_post(pid, name, data, text="", day=0, extra=()):
    media = [MediaItem(kind="document", file_name=name, size=len(data), source_ref=data), *extra]
    return ChannelPost(id=pid, date=BASE + timedelta(days=day), text=text, media=media,
                       url=f"https://t.me/testchan/{pid}")


def make_pdf(scanned_page: bool = True) -> bytes:
    from versline.services.document_processor import _import_pymupdf

    fitz = _import_pymupdf()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "First page with a real text layer, long enough.")
    if scanned_page:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
        pix.clear_with(200)
        doc.new_page().insert_image(fitz.Rect(50, 50, 300, 300), pixmap=pix)
    data = doc.tobytes()
    doc.close()
    return data


def make_docx(text: str) -> bytes:
    import io

    from docx import Document

    document = Document()
    document.add_heading("عنوان جزوه", level=1)
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class TestCleanForObsidian(unittest.TestCase):
    def test_presentation_forms_controls_links_and_data_images(self):
        raw = "ﺳﻼﻡ ﷺ\x00 [[x]] %%hidden%%\r\n![](data:image/png;base64,AAAA)\n\n\n\nend"
        cleaned = docs.clean_for_obsidian(raw)
        self.assertIn("سلام ﷺ", cleaned)
        self.assertNotIn("\x00", cleaned)
        self.assertIn(r"\[\[x\]\]", cleaned)
        self.assertIn(r"\%\%hidden\%\%", cleaned)
        self.assertNotIn("data:image", cleaned)
        self.assertNotIn("\n\n\n", cleaned)

    def test_is_convertible(self):
        self.assertTrue(docs.is_convertible(MediaItem(kind="document", file_name="a.PDF")))
        self.assertTrue(docs.is_convertible(MediaItem(kind="document", mime="application/pdf")))
        self.assertFalse(docs.is_convertible(MediaItem(kind="document", file_name="a.zip")))
        self.assertFalse(docs.is_convertible(MediaItem(kind="audio", file_name="a.pdf")))
        image = MediaItem(kind="document", file_name="scan.jpg")
        self.assertFalse(docs.is_convertible(image))
        self.assertTrue(docs.is_convertible(image, ocr=True))


class TestUpsertSection(unittest.TestCase):
    NOTE = "---\ntitle: \"x\"\n---\n\n# x\n\n## توضیحات\n\nکپشن\n\n## پیوست‌ها\n\n![[a.pdf]]\n\n---\n[پست اصلی](https://t.me/c/1)\n"

    def test_inserts_before_attachments_and_replaces_existing(self):
        once = obsidian.upsert_section(self.NOTE, "documents", "- [[documents/a|a.pdf]]")
        self.assertLess(once.index("## اسناد"), once.index("## پیوست‌ها"))
        self.assertIn("کپشن", once)
        twice = obsidian.upsert_section(once, "documents", "- [[documents/b|b.pdf]]")
        self.assertEqual(twice.count("## اسناد"), 1)
        self.assertNotIn("documents/a", twice)
        self.assertIn("![[a.pdf]]", twice)

    def test_without_attachments_goes_before_the_footer(self):
        note = "# x\n\nمتن\n\n---\n[پست اصلی](https://t.me/c/1)\n"
        out = obsidian.upsert_section(note, "documents", "- [[documents/a|a.pdf]]")
        self.assertLess(out.index("## اسناد"), out.index("[پست اصلی]"))


class TestConvertDocument(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_pdf_scanned_page_without_ocr_warns(self):
        path = self.tmp / "a.pdf"
        path.write_bytes(make_pdf())
        result = docs.convert_document(path)
        self.assertEqual((result.pages, result.ocr_pages, result.unread_pages), (2, 0, 1))
        self.assertIn("First page", result.text)
        self.assertIn("%% صفحه ۱ %%", result.text)
        self.assertTrue(any("--ocr" in w for w in result.warnings))

    def test_pdf_ocr_reads_only_the_scanned_page_and_caches_it(self):
        path = self.tmp / "a.pdf"
        path.write_bytes(make_pdf())
        llm = FakeVisionLLM()
        cache = self.tmp / docs.OCR_CACHE_NAME
        result = docs.convert_document(path, ocr=docs.OcrReader(llm, cache))
        self.assertEqual((result.converter, result.ocr_pages, result.unread_pages), ("pymupdf+ocr", 1, 0))
        self.assertEqual(llm.images, ["a_p2.png"])
        self.assertIn("متن صفحه‌ی اسکن‌شده", result.text)
        self.assertNotIn("بله", result.text)
        self.assertFalse((self.tmp / "a_p2.png").exists())
        again = FakeVisionLLM()
        docs.convert_document(path, ocr=docs.OcrReader(again, cache))
        self.assertEqual(again.images, [])  # cached
        forced = FakeVisionLLM()
        docs.convert_document(path, ocr=docs.OcrReader(forced, cache, force=True))
        self.assertEqual(forced.images, ["a_p2.png"])

    def test_ocr_all_pages_reads_text_pages_too(self):
        path = self.tmp / "a.pdf"
        path.write_bytes(make_pdf())
        llm = FakeVisionLLM()
        result = docs.convert_document(path, ocr=docs.OcrReader(llm, None, all_pages=True))
        self.assertEqual((sorted(llm.images), result.converter), (["a_p1.png", "a_p2.png"], "ocr"))
        self.assertNotIn("First page", result.text)

    def test_ocr_max_pages_caps_new_reads(self):
        path = self.tmp / "a.pdf"
        path.write_bytes(make_pdf())
        llm = FakeVisionLLM()
        result = docs.convert_document(path, ocr=docs.OcrReader(llm, None, max_pages=0))
        self.assertEqual((llm.images, result.unread_pages), ([], 1))
        self.assertIn("--ocr-max-pages", result.text)

    def test_text_and_docx(self):
        txt = self.tmp / "n.txt"
        txt.write_text("سطر اول\n\n\n\nسطر دوم", encoding="utf-8")
        self.assertEqual(docs.convert_document(txt).text, "سطر اول\n\nسطر دوم")
        docx = self.tmp / "j.docx"
        docx.write_bytes(make_docx("متن بند"))
        result = docs.convert_document(docx)
        self.assertEqual(result.converter, "markitdown")
        self.assertIn("# عنوان جزوه", result.text)
        self.assertIn("متن بند", result.text)


class TestArchiveToMarkdown(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "out"

    def run_archive(self, posts, steps=STEPS, to_markdown=True, ocr=None, files_only=False, keep_media=False,
                    transcriber=None, **opts):
        source = FileSource(posts)
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp",
                          transcriber=transcriber or FakeTranscriber(), to_markdown=to_markdown, ocr=ocr,
                          keep_media=keep_media)
        options = ArchiveOptions(out_dir=self.out, temp_dir=ctx.temp_dir, steps=steps, files_only=files_only, **opts)
        summary = ChannelArchiver(source, ctx, options).run("@testchan")
        return summary, source, ctx

    def manifest(self, name=".versline-channel.json"):
        return json.loads((self.out / name).read_text(encoding="utf-8"))["posts"]

    def post_note(self):
        return next((self.out / "posts").glob("*.md")).read_text(encoding="utf-8")

    def test_document_note_with_frontmatter_and_backlinks(self):
        posts = [doc_post(1, "جزوه فقه.docx", make_docx("متن بند"), text="#فقه جزوه جلسه اول")]
        summary, source, _ = self.run_archive(posts)
        self.assertEqual((summary.done, summary.failed), (1, 0))
        note = (self.out / "documents" / "جزوه فقه.md").read_text(encoding="utf-8")
        self.assertIn('type: "telegram-document"', note)
        self.assertIn('post: "[[posts/2026-03-01 - 1 - جزوه جلسه اول]]"', note)
        self.assertIn('tags: ["telegram", "document", "فقه"]', note)
        self.assertIn("متن بند", note)
        self.assertNotIn("source_file", note)  # not kept without --keep-media
        self.assertIn("## اسناد\n\n- [[documents/جزوه فقه|جزوه فقه.docx]]", self.post_note())
        self.assertEqual(self.manifest()["1"]["documents"],
                         [{"index": 0, "file": "جزوه فقه.docx", "note": "documents/جزوه فقه.md"}])
        self.assertTrue(all(not p.exists() for p in source.downloads))

    def test_keep_media_links_the_attachment(self):
        posts = [doc_post(1, "a.txt", b"hello text")]
        self.run_archive(posts, keep_media=True)
        note = (self.out / "documents" / "a.md").read_text(encoding="utf-8")
        self.assertIn('source_file: "[[attachments/testchan_1.txt]]"', note)

    def test_same_name_in_two_posts_gets_post_suffix(self):
        posts = [doc_post(1, "a.txt", b"one"), doc_post(2, "a.txt", b"two", day=1)]
        self.run_archive(posts)
        self.assertEqual(sorted(p.name for p in (self.out / "documents").iterdir()), ["a (post 2).md", "a.md"])

    def test_failed_conversion_keeps_the_post(self):
        posts = [doc_post(1, "broken.docx", b"not a zip")]
        with mock.patch.object(docs, "convert_document", side_effect=RuntimeError("unreadable")):
            summary, _, _ = self.run_archive(posts)
        self.assertEqual((summary.done, summary.failed), (1, 0))
        self.assertTrue(any("broken.docx" in e for e in summary.errors))
        self.assertIn("document not converted: broken.docx", self.post_note())
        self.assertIn("error", self.manifest()["1"]["documents"][0])

    def test_rerun_adds_documents_to_an_old_archive_without_touching_the_rest(self):
        audio = MediaItem(kind="audio", duration=30, size=5, source_ref=object())
        posts = [doc_post(1, "a.txt", b"doc text", text="کپشن", extra=[audio])]
        self.run_archive(posts, to_markdown=False, steps=["media", "transcribe"])
        note_path = next((self.out / "posts").glob("*.md"))
        note_path.write_text(note_path.read_text(encoding="utf-8").replace("کپشن", "کپشن ویرایش‌شده"), encoding="utf-8")
        transcriber = FakeTranscriber()
        summary, source, _ = self.run_archive(posts, transcriber=transcriber)
        self.assertEqual((summary.done, summary.skipped), (1, 0))
        self.assertEqual(transcriber.calls, [])
        self.assertEqual([p.suffix for p in source.downloads], [".txt"])
        note = note_path.read_text(encoding="utf-8")
        self.assertIn("کپشن ویرایش‌شده", note)
        self.assertIn("transcript of", note)
        self.assertIn("[[documents/a|a.txt]]", note)
        self.assertTrue((self.out / "documents" / "a.md").is_file())
        summary, source, _ = self.run_archive(posts)
        self.assertEqual((summary.done, summary.skipped, source.downloads), (0, 1, []))

    def test_force_without_to_markdown_keeps_the_links(self):
        posts = [doc_post(1, "a.txt", b"doc text")]
        self.run_archive(posts)
        self.run_archive(posts, to_markdown=False, steps=["media", "transcribe"], force=True)
        self.assertIn("[[documents/a|a.txt]]", self.post_note())
        self.assertEqual(self.manifest()["1"]["documents"][0]["note"], "documents/a.md")

    def test_ocr_retries_scanned_pages_left_unread(self):
        posts = [doc_post(1, "scan.pdf", make_pdf())]
        self.run_archive(posts)
        self.assertEqual(self.manifest()["1"]["documents"][0]["unread_pages"], 1)
        llm = FakeVisionLLM()
        summary, _, _ = self.run_archive(posts, ocr=docs.OcrReader(llm, model="vision-model"))
        self.assertEqual(summary.done, 1)
        self.assertEqual(len(llm.images), 1)
        note = (self.out / "documents" / "scan.md").read_text(encoding="utf-8")
        self.assertIn("متن صفحه‌ی اسکن‌شده", note)
        self.assertIn('ocr_model: "vision-model"', note)
        self.assertNotIn("unread_pages", self.manifest()["1"]["documents"][0])
        self.assertTrue((self.out / docs.OCR_CACHE_NAME).is_file())

    def test_files_only_writes_a_note_next_to_each_file(self):
        posts = [doc_post(1, "a.txt", b"one"), doc_post(2, "a.txt", b"one", day=1), doc_post(3, "readme.md", b"# hi", day=2)]
        summary, _, _ = self.run_archive(posts, files_only=True)
        self.assertEqual((summary.files_saved, summary.duplicates), (2, 1))
        note = (self.out / "a.md").read_text(encoding="utf-8")
        self.assertIn('source_file: "[[a.txt]]"', note)
        self.assertNotIn("post:", note)
        self.assertEqual(sorted(p.name for p in self.out.glob("*.md")), ["a.md", "readme.md"])  # md files stay as they are
        self.assertEqual(self.manifest(".versline-files.json")["2"]["notes"][0]["note"], "a.md")

    def test_files_only_rerun_adds_notes_without_downloading(self):
        posts = [doc_post(1, "a.txt", b"one")]
        self.run_archive(posts, files_only=True, to_markdown=False)
        summary, source, _ = self.run_archive(posts, files_only=True)
        self.assertEqual((summary.done, source.downloads), (1, []))
        self.assertTrue((self.out / "a.md").is_file())
        self.assertEqual(self.manifest(".versline-files.json")["1"]["files"], ["a.txt"])


class TestArchiveCommand(unittest.TestCase):
    def test_files_only_with_ocr_through_the_cli(self):
        from typer.testing import CliRunner

        from versline.commands import telegram as cmd
        from versline.services.channel_archive.llm import TextLLM

        out = Path(tempfile.mkdtemp()) / "out"
        llm = FakeVisionLLM()
        with mock.patch.object(cmd, "_make_source", return_value=FileSource([doc_post(1, "scan.pdf", make_pdf())])), \
                mock.patch.object(cmd, "_require_llm"), \
                mock.patch.object(TextLLM, "generate_with_image", lambda self, prompt, image: llm.generate_with_image(prompt, image)):
            result = CliRunner().invoke(cmd.app, ["archive", "@testchan", "--files-only", "--ocr", "-o", str(out)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(llm.images, ["scan_p2.png"])
        self.assertIn("متن صفحه‌ی اسکن‌شده", (out / "scan.md").read_text(encoding="utf-8"))
        self.assertTrue((out / docs.OCR_CACHE_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
