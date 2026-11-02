import unittest
from datetime import datetime, timezone

from versline.services.channel_archive.filters import FileFilter, item_extension, normalize_fa
from versline.services.channel_archive.models import ChannelPost, MediaItem

DATE = datetime(2026, 3, 1, tzinfo=timezone.utc)


def doc(name=None, mime=None):
    return MediaItem(kind="document", file_name=name, mime=mime)


def post(*items, text=""):
    return ChannelPost(id=1, date=DATE, text=text, media=list(items))


def accepts(flt, item, text=""):
    return flt.accepts(post(item, text=text), item)


class TestNormalize(unittest.TestCase):
    def test_persian_variants_zwnj_and_underscore(self):
        self.assertEqual(normalize_fa("جزوه_فقه"), normalize_fa("جزوه‌فقه"))
        self.assertEqual(normalize_fa("علي كتاب"), "علی کتاب")
        self.assertEqual(normalize_fa("كتــاب"), "کتاب")

    def test_pattern_regex_classes_survive(self):
        flt = FileFilter.build(match=[r"\D+_(\d+)"])
        self.assertTrue(accepts(flt, doc("abc_12.pdf")))
        self.assertFalse(accepts(flt, doc("12.pdf")))

    def test_pattern_with_arabic_letters_matches_persian_name(self):
        flt = FileFilter.build(match=["علي"])
        self.assertTrue(accepts(flt, doc("درس_علی.pdf")))


class TestExtension(unittest.TestCase):
    def test_name_then_mime(self):
        self.assertEqual(item_extension(doc("A.PDF")), "pdf")
        self.assertEqual(item_extension(doc(None, "application/pdf")), "pdf")
        self.assertEqual(item_extension(doc("noext", "application/msword")), "doc")
        self.assertIsNone(item_extension(doc("noext")))

    def test_word_alias_and_case(self):
        flt = FileFilter.build(ext="pdf, word")
        self.assertTrue(accepts(flt, doc("a.DOCX")))
        self.assertTrue(accepts(flt, doc("a.doc")))
        self.assertTrue(accepts(flt, doc(None, "application/pdf")))
        self.assertFalse(accepts(flt, doc("a.zip")))
        self.assertFalse(accepts(flt, MediaItem(kind="photo")))


class TestPatterns(unittest.TestCase):
    def test_include_is_or_and_case_insensitive(self):
        flt = FileFilter.build(match=["jozve", "خلاصه"])
        self.assertTrue(accepts(flt, doc("JOZVE_1.pdf")))
        self.assertTrue(accepts(flt, doc("خلاصه درس.pdf")))
        self.assertFalse(accepts(flt, doc("other.pdf")))

    def test_exclude_wins(self):
        flt = FileFilter.build(match=["جزوه"], exclude=["پیش‌نویس|draft"])
        self.assertTrue(accepts(flt, doc("جزوه فقه.pdf")))
        self.assertFalse(accepts(flt, doc("جزوه_پیش_نویس.pdf")))
        self.assertFalse(accepts(flt, doc("جزوه پیش نویس.pdf")))
        self.assertFalse(accepts(flt, doc("جزوه DRAFT.pdf")))

    def test_exclude_only(self):
        flt = FileFilter.build(exclude=["draft"])
        self.assertTrue(accepts(flt, doc("final.pdf")))
        self.assertFalse(accepts(flt, doc("draft.pdf")))

    def test_match_in_caption_and_any(self):
        item = doc("file1.pdf")
        by_name = FileFilter.build(match=["جزوه"], match_in="name")
        by_caption = FileFilter.build(match=["جزوه"], match_in="caption")
        by_any = FileFilter.build(match=["جزوه"], match_in="any")
        self.assertFalse(accepts(by_name, item, text="جزوه جدید"))
        self.assertTrue(accepts(by_caption, item, text="جزوه جدید"))
        self.assertTrue(accepts(by_any, item, text="جزوه جدید"))
        self.assertTrue(accepts(by_any, doc("جزوه.pdf"), text="چیز دیگر"))

    def test_exclude_in_any_checks_both(self):
        flt = FileFilter.build(exclude=["draft"], match_in="any")
        self.assertFalse(accepts(flt, doc("a.pdf"), text="this is a draft"))

    def test_matching_indices_per_item(self):
        flt = FileFilter.build(ext="pdf")
        p = post(MediaItem(kind="photo"), doc("a.pdf"), doc("b.zip"), doc("c.pdf"))
        self.assertEqual(flt.matching_indices(p), [1, 3])


class TestBuild(unittest.TestCase):
    def test_nothing_given_is_none(self):
        self.assertIsNone(FileFilter.build())
        self.assertIsNone(FileFilter.build(ext=" , "))

    def test_bad_regex_and_target(self):
        with self.assertRaises(ValueError) as ctx:
            FileFilter.build(match=["("])
        self.assertIn("--match", str(ctx.exception))
        with self.assertRaises(ValueError):
            FileFilter.build(match_in="body")


if __name__ == "__main__":
    unittest.main()
