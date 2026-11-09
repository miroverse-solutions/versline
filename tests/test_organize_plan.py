import csv
import os
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from versline.commands import organize as organize_cmd
from versline.services.organize import (
    Catalog, apply_plan, build_plan, find_duplicates, parse_rules, read_plan, revert_moves, scan_sources, verify,
    write_plan,
)
from versline.services.organize.rules import outside_taxonomy

RULES = """
@dest_root مرتب
@default ۹-بایگانی خام
@root_priority lib | old
@media ۱-کتابخانه => ۲-صوت و تصویر
@media ۹-بایگانی خام => ۲-صوت و تصویر/۹-بایگانی خام
lib/فقه => ۱-کتابخانه/اصول و فقه      # Persian letters in the rule, Arabic ك/ي on disk must still match
lib/علوم/ژنتیک.pdf => ۱-کتابخانه/علوم روز/زیست‌شناسی
old/کتابخانه/فقه => ۱-کتابخانه/اصول و فقه
old/پروژه => ۳-نوشته‌ها و پروژه‌ها/پروژه
"""


class RulesTests(unittest.TestCase):
    def test_parse_and_match(self):
        rules = parse_rules(RULES + "\nbroken line\n@unknown x\n")
        self.assertEqual(rules.dest_root, "مرتب")
        self.assertEqual(len(rules.errors), 2)
        rule, rest = rules.match("lib", "فقه/كتب/a.pdf")
        self.assertEqual((rule.dest, rest), ("۱-کتابخانه/اصول و فقه", "كتب/a.pdf"))
        rule, rest = rules.match("lib", "علوم/ژنتیک.pdf")
        self.assertEqual((rule.dest, rest), ("۱-کتابخانه/علوم روز/زیست‌شناسی", "ژنتیک.pdf"))
        self.assertEqual(rules.match("lib", "other/x.pdf")[0], None)
        self.assertEqual(rules.media_dest("۱-کتابخانه/اصول و فقه/درس/1.mp3"), "۲-صوت و تصویر/اصول و فقه/درس/1.mp3")
        self.assertEqual(rules.media_dest("۳-نوشته‌ها و پروژه‌ها/x.mp4"), "۳-نوشته‌ها و پروژه‌ها/x.mp4")

    def test_taxonomy_check(self):
        taxonomy = ["۱-کتابخانه/اصول و فقه", "۳-نوشته‌ها و پروژه‌ها"]
        self.assertFalse(outside_taxonomy("۱-کتابخانه/اصول و فقه/کتب/a.pdf", taxonomy))
        self.assertFalse(outside_taxonomy("۳-نوشته‌ها و پروژه‌ها/x/y.pdf", taxonomy))
        self.assertTrue(outside_taxonomy("۱-کتابخانه/نامعلوم/a.pdf", taxonomy))


class PlanApplyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.drive = Path(self._tmp.name)
        lib, old = self.drive / "lib", self.drive / "old"
        self.files = {
            lib / "فقه" / "كتب" / "a.pdf": b"book A",
            lib / "فقه" / "درس" / "جلسه 1.mp3": b"M" * 5000,
            lib / "فقه" / "درس" / "جزوه.pdf": b"handout",          # follows the media-heavy folder
            lib / "علوم" / "ژنتیک.pdf": b"genetics",
            lib / "علوم" / "Thumbs.db": b"junk",
            old / "کتابخانه" / "فقه" / "a copy.pdf": b"book A",   # duplicate of lib's a.pdf
            old / "کتابخانه" / "فقه" / "کتب" / "a.pdf": b"other book with same dest",
            old / "پروژه" / "voice.mp3": b"V" * 100,
            old / "دانلود" / "x.docx": b"unknown",
        }
        for path, data in self.files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.workspace = self.drive / "_versline_organize"
        self.workspace.mkdir()
        (self.workspace / "rules.txt").write_text(RULES, encoding="utf-8")
        self.catalog = Catalog(self.workspace)
        scan_sources(self.catalog, [lib, old])
        find_duplicates(self.catalog)
        self.rules = parse_rules(RULES)
        self.dest = self.drive / "مرتب"

    def tearDown(self):
        self.catalog.close()
        self._tmp.cleanup()

    def plan(self):
        rows, stats = build_plan(self.catalog, self.rules)
        path = self.workspace / "plan" / "plan.csv"
        write_plan(rows, path)
        return {(r.root, r.path): r for r in rows}, read_plan(path), stats

    def test_plan_actions_and_destinations(self):
        rows, _, stats = self.plan()
        self.assertEqual(rows[("lib", "فقه/كتب/a.pdf")].dest, "۱-کتابخانه/اصول و فقه/کتب/a.pdf")
        media = rows[("lib", "فقه/درس/جلسه 1.mp3")]
        self.assertEqual((media.action, media.dest), ("move", "۲-صوت و تصویر/اصول و فقه/درس/جلسه 1.mp3"))
        handout = rows[("lib", "فقه/درس/جزوه.pdf")]
        self.assertEqual((handout.action, handout.dest, handout.note),
                         ("copy", "۲-صوت و تصویر/اصول و فقه/درس/جزوه.pdf", "with-media"))
        self.assertEqual(rows[("lib", "علوم/ژنتیک.pdf")].dest, "۱-کتابخانه/علوم روز/زیست‌شناسی/ژنتیک.pdf")
        self.assertEqual(rows[("lib", "علوم/Thumbs.db")].action, "skip_junk")
        duplicate = rows[("old", "کتابخانه/فقه/a copy.pdf")]
        self.assertEqual((duplicate.action, duplicate.duplicate_of), ("skip_duplicate", "۱-کتابخانه/اصول و فقه/کتب/a.pdf"))
        clash = rows[("old", "کتابخانه/فقه/کتب/a.pdf")]
        self.assertEqual((clash.dest, clash.note), ("۱-کتابخانه/اصول و فقه/کتب/a (2).pdf", "renamed-collision"))
        self.assertEqual(stats["collisions"], 1)
        self.assertEqual(rows[("old", "پروژه/voice.mp3")].dest, "۳-نوشته‌ها و پروژه‌ها/پروژه/voice.mp3")
        self.assertEqual(rows[("old", "دانلود/x.docx")].dest, "۹-بایگانی خام/old/دانلود/x.docx")

    def test_assignments_win_over_rules(self):
        from versline.services.organize.rules import load_assignments
        path = self.workspace / "assignments.csv"
        path.write_text("root,path,dest,by,note\nold,دانلود/x.docx,۱-کتابخانه/تاریخ,claude,\n"
                        "lib,فقه/درس/جلسه 1.mp3,۱-کتابخانه/اخلاق و عبادات,claude,\n", encoding="utf-8-sig")
        self.assertEqual(load_assignments(path, self.rules), 2)
        rows, _, _ = self.plan()
        self.assertEqual((rows[("old", "دانلود/x.docx")].dest, rows[("old", "دانلود/x.docx")].rule),
                         ("۱-کتابخانه/تاریخ/x.docx", "assign:claude"))
        self.assertEqual(rows[("lib", "فقه/درس/جلسه 1.mp3")].dest, "۲-صوت و تصویر/اخلاق و عبادات/جلسه 1.mp3")

    def test_collision_keeps_plain_name_for_priority_source(self):
        self.rules = parse_rules(RULES.replace("@root_priority lib | old", "@root_priority old | lib"))
        rows, _, _ = self.plan()
        self.assertEqual(rows[("old", "کتابخانه/فقه/کتب/a.pdf")].dest, "۱-کتابخانه/اصول و فقه/کتب/a.pdf")
        self.assertEqual(rows[("lib", "فقه/كتب/a.pdf")].action, "skip_duplicate")  # old's 'a copy.pdf' is kept

    def test_apply_verify_resume_and_revert(self):
        _, plan, _ = self.plan()
        dry = apply_plan(self.catalog, plan, self.dest, dry_run=True)
        self.assertEqual((dry.moved, dry.copied), (2, 5))
        self.assertFalse(self.dest.exists())

        result = apply_plan(self.catalog, plan, self.dest)
        self.assertEqual((result.moved, result.copied, result.errors), (2, 5, 0))
        moved = self.dest / "۲-صوت و تصویر" / "اصول و فقه" / "درس" / "جلسه 1.mp3"
        self.assertEqual(moved.read_bytes(), b"M" * 5000)
        self.assertFalse((self.drive / "lib" / "فقه" / "درس" / "جلسه 1.mp3").exists())
        self.assertTrue((self.drive / "lib" / "فقه" / "كتب" / "a.pdf").exists())  # copies leave sources alone
        self.assertEqual((self.dest / "۱-کتابخانه" / "اصول و فقه" / "کتب" / "a (2).pdf").read_bytes(),
                         b"other book with same dest")
        with open(self.workspace / "logs" / "moves.csv", encoding="utf-8-sig", newline="") as handle:
            logged = list(csv.DictReader(handle))
        self.assertEqual(len(logged), 2)
        self.assertIn("lib/فقه/درس/جلسه 1.mp3", [r["from"] for r in logged])
        self.assertIn("مرتب/۲-صوت و تصویر/اصول و فقه/درس/جلسه 1.mp3", [r["to"] for r in logged])

        again = apply_plan(self.catalog, plan, self.dest)  # resumable / idempotent
        self.assertEqual((again.moved, again.copied, again.skipped), (0, 0, 7))

        counts = verify(self.catalog, plan, self.dest, deep=True)
        self.assertEqual(counts, {"copied": 5, "moved": 2, "skipped_junk": 1, "duplicate_ok": 1})

        reverted = revert_moves(self.catalog, self.dest)
        self.assertEqual(reverted["reverted"], 2)
        self.assertTrue((self.drive / "lib" / "فقه" / "درس" / "جلسه 1.mp3").exists())
        self.assertFalse(moved.exists())
        with open(self.workspace / "logs" / "moves.csv", encoding="utf-8-sig", newline="") as handle:
            self.assertEqual({r["status"] for r in csv.DictReader(handle)}, {"reverted"})

    def test_existing_different_file_is_never_overwritten(self):
        _, plan, _ = self.plan()
        target = self.dest / "۹-بایگانی خام" / "old" / "دانلود" / "x.docx"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"something else")
        result = apply_plan(self.catalog, plan, self.dest, only="copy")
        self.assertEqual(result.errors, 1)
        self.assertEqual(target.read_bytes(), b"something else")

    def test_skip_unclassified_then_complete(self):
        _, plan, _ = self.plan()
        first = apply_plan(self.catalog, plan, self.dest, skip_unclassified=True)
        self.assertEqual((first.moved, first.copied), (2, 4))
        self.assertFalse((self.dest / "۹-بایگانی خام").exists())
        second = apply_plan(self.catalog, plan, self.dest)
        self.assertEqual((second.moved, second.copied), (0, 1))

    def test_unapproved_rows_are_skipped(self):
        _, plan, _ = self.plan()
        for row in plan:
            if row["action"] == "move":
                row["approved"] = "no"
        result = apply_plan(self.catalog, plan, self.dest)
        self.assertEqual(result.moved, 0)
        self.assertTrue((self.drive / "lib" / "فقه" / "درس" / "جلسه 1.mp3").exists())

    def test_cli_plan_apply_verify(self):
        self.catalog.close()
        runner = CliRunner()
        ws = str(self.workspace)
        result = runner.invoke(organize_cmd.app, ["plan", "-w", ws])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.workspace / "plan" / "plan_summary.md").is_file())
        with open(self.workspace / "plan" / "plan.csv", encoding="utf-8-sig") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), len(self.files))
        result = runner.invoke(organize_cmd.app, ["apply", "-w", ws, "--dry-run"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(self.dest.exists())
        result = runner.invoke(organize_cmd.app, ["apply", "-w", ws, "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        result = runner.invoke(organize_cmd.app, ["verify", "-w", ws])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("✅", (self.workspace / "reports" / "verify.md").read_text(encoding="utf-8"))
        result = runner.invoke(organize_cmd.app, ["revert-moves", "-w", ws, "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.catalog = Catalog(self.workspace)  # reopened for tearDown


if __name__ == "__main__":
    unittest.main()
