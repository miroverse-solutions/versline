import csv
import os
import tempfile
import time
import unittest
from pathlib import Path

from typer.testing import CliRunner

from versline.commands import organize as organize_cmd
from versline.services.organize import (
    Catalog, duplicate_groups, export_files, find_duplicates, redundant_folders, scan_sources, write_duplicates,
    write_stats,
)
from versline.services.organize.hashing import PARTIAL_BYTES, full_hash
from versline.services.organize.kinds import classify_kind
from versline.services.organize.normalize import norm_name, normalize_text, windows_safe_name


class NormalizeTests(unittest.TestCase):
    def test_arabic_letters_become_persian(self):
        self.assertEqual(normalize_text("كتاب  الكافي"), "کتاب الکافی")

    def test_norm_name_drops_diacritics_and_case(self):
        self.assertEqual(norm_name("القُرآن Book.PDF"), norm_name("القرآن book.pdf"))

    def test_windows_safe_name(self):
        self.assertEqual(windows_safe_name('a:b?c.pdf'), "a_b_c.pdf")
        self.assertEqual(windows_safe_name("name. "), "name")
        self.assertEqual(windows_safe_name("CON.txt"), "CON_.txt")
        long_name = windows_safe_name("ا" * 300 + ".pdf", max_len=100)
        self.assertTrue(long_name.endswith(".pdf"))
        self.assertLessEqual(len(long_name), 100)


class KindTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify_kind("x.PDF"), "book")
        self.assertEqual(classify_kind("جلسه 1.mp3"), "audio")
        self.assertEqual(classify_kind("Thumbs.db"), "junk")
        self.assertEqual(classify_kind("~$doc.docx"), "junk")
        self.assertEqual(classify_kind("setup.exe"), "software")
        self.assertEqual(classify_kind("README"), "other")


class OrganizeServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.drive = Path(self._tmp.name)
        self.lib = self.drive / "کتابخانه"
        self.old = self.drive / "هارد قدیمی"
        big = os.urandom(3 * PARTIAL_BYTES + 10)
        self.write(self.lib / "تفسیر" / "المیزان.pdf", big)
        self.write(self.lib / "تفسیر" / "notes.docx", b"notes")
        self.write(self.lib / "same-size-a.pdf", b"A" * 1000)
        self.write(self.lib / "same-size-b.pdf", b"B" * 1000)
        self.write(self.lib / "empty.txt", b"")
        # a full copy of the tafsir folder inside the old drive dump
        self.write(self.old / "backup" / "تفسیر" / "المیزان.pdf", big)
        self.write(self.old / "backup" / "تفسیر" / "notes.docx", b"notes")
        self.write(self.old / "empty-copy.txt", b"")
        for index in range(12):
            self.write(self.old / "scan" / f"{index:03d}.jpg", bytes([index]) * 50)
        self.write(self.old / "$RECYCLE.BIN" / "deleted.pdf", b"x")
        self.workspace = self.drive / "_versline_organize"

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def catalog(self):
        return Catalog(self.workspace)

    def test_scan_stores_relative_roots_and_skips_system_folders(self):
        with self.catalog() as catalog:
            result = scan_sources(catalog, [self.lib, self.old])
            self.assertEqual(result.files, 5 + 3 + 12)
            paths = [r["path"] for r in catalog.roots()]
            self.assertEqual(paths, ["کتابخانه", "هارد قدیمی"])
            self.assertEqual(catalog.root_path(1), self.lib)
            names = [r[0] for r in catalog.conn.execute("SELECT name FROM files")]
            self.assertNotIn("deleted.pdf", names)
            scan_dir = catalog.conn.execute("SELECT dir_kind FROM dirs WHERE relpath='scan'").fetchone()[0]
            self.assertEqual(scan_dir, "scan_folder")

    def test_rescan_is_incremental(self):
        with self.catalog() as catalog:
            scan_sources(catalog, [self.lib, self.old])
            find_duplicates(catalog)
            hashed_before = catalog.conn.execute("SELECT COUNT(full_hash) FROM files").fetchone()[0]
            self.assertGreater(hashed_before, 0)

            (self.lib / "same-size-a.pdf").unlink()
            changed = self.lib / "تفسیر" / "notes.docx"
            changed.write_bytes(b"notes v2")
            os.utime(changed, (time.time() + 100, time.time() + 100))
            result = scan_sources(catalog, [self.lib, self.old])
            self.assertEqual((result.new, result.changed, result.missing), (0, 1, 1))
            row = catalog.conn.execute(
                "SELECT full_hash FROM files WHERE relpath='تفسیر/notes.docx' AND root_id=1").fetchone()
            self.assertIsNone(row[0])
            present = catalog.conn.execute(
                "SELECT present FROM files WHERE relpath='same-size-a.pdf'").fetchone()[0]
            self.assertEqual(present, 0)

    def test_duplicates_and_redundant_folders(self):
        with self.catalog() as catalog:
            scan_sources(catalog, [self.lib, self.old])
            summary = find_duplicates(catalog)
            groups = duplicate_groups(catalog)
            self.assertEqual(summary.groups, 2)  # المیزان.pdf and notes.docx; empty files are ignored
            self.assertEqual(len(groups), 2)
            big = groups[0]
            self.assertEqual(big["hash"], full_hash(self.lib / "تفسیر" / "المیزان.pdf"))
            self.assertEqual(sorted(m[1] for m in big["members"]), sorted(["کتابخانه", "هارد قدیمی"]))
            # same size but different content must not be grouped
            distinct = catalog.conn.execute(
                "SELECT COUNT(DISTINCT partial_hash) FROM files WHERE name LIKE 'same-size-%'").fetchone()[0]
            self.assertEqual(distinct, 2)

            # the two roots themselves are ~99% duplicated too; a stricter ratio isolates the copied folders
            folders = redundant_folders(catalog, groups, min_ratio=0.999, min_bytes=1)
            names = [f["folder"] for f in folders]
            self.assertIn("هارد قدیمی/backup", names)
            self.assertIn("کتابخانه/تفسیر", names)
            self.assertNotIn("هارد قدیمی/backup/تفسیر", names)  # only the top-most folder of a branch
            backup = next(f for f in folders if f["folder"] == "هارد قدیمی/backup")
            self.assertEqual(backup["elsewhere"], "کتابخانه/تفسیر")

    def test_errors_are_refreshed_not_accumulated(self):
        with self.catalog() as catalog:
            for _ in range(3):
                catalog.add_error(1, "a/b.pdf", "hash-partial", "OSError")
            count = catalog.conn.execute("SELECT COUNT(*) FROM scan_errors").fetchone()[0]
            self.assertEqual(count, 1)
            scan_sources(catalog, [self.lib])
            find_duplicates(catalog)
            count = catalog.conn.execute("SELECT COUNT(*) FROM scan_errors").fetchone()[0]
            self.assertEqual(count, 0)

    def test_reports_are_excel_friendly(self):
        with self.catalog() as catalog:
            scan_sources(catalog, [self.lib, self.old])
            find_duplicates(catalog)
            groups = duplicate_groups(catalog)
            write_duplicates(catalog, groups, redundant_folders(catalog, groups, min_bytes=1))
            write_stats(catalog)
            files_csv = export_files(catalog)
        reports = self.workspace / "reports"
        for name in ("stats.md", "duplicates.md", "duplicates.csv", "redundant_folders.csv", "scan_folders.csv",
                     "files.csv"):
            self.assertTrue((reports / name).is_file(), name)
        self.assertTrue(files_csv.read_bytes().startswith(b"\xef\xbb\xbf"))
        with open(files_csv, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 20)
        tafsir = next(r for r in rows if r["path"] == "تفسیر/المیزان.pdf")
        self.assertEqual(tafsir["copies"], "2")


class OrganizeCliTests(unittest.TestCase):
    def test_scan_dupes_status_export(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            drive = Path(tmp)
            src = drive / "src"
            (src / "a").mkdir(parents=True)
            (src / "a" / "x.pdf").write_bytes(b"same content")
            (src / "b").mkdir()
            (src / "b" / "x copy.pdf").write_bytes(b"same content")
            workspace = drive / "_versline_organize"
            for args in (["scan", str(src), "-w", str(workspace)], ["dupes", "-w", str(workspace)],
                         ["status", "-w", str(workspace)], ["export", "-w", str(workspace)]):
                result = runner.invoke(organize_cmd.app, args)
                self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue((workspace / "reports" / "duplicates.md").is_file())
            self.assertTrue((workspace / "logs" / "organize.log").is_file())

    def test_missing_workspace_fails_cleanly(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(organize_cmd.app, ["status", "-w", str(Path(tmp) / "nothing")])
            self.assertEqual(result.exit_code, 1)

    def test_parse_size(self):
        self.assertEqual(organize_cmd.parse_size("1"), 1)
        self.assertEqual(organize_cmd.parse_size("10MB"), 10 * 1024 * 1024)
        self.assertEqual(organize_cmd.parse_size("1.5 kb"), 1536)


if __name__ == "__main__":
    unittest.main()
