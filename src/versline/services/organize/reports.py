"""Human-readable reports (Markdown in Persian, CSV in UTF-8 with BOM so Excel shows Persian correctly)."""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from versline.services.organize.catalog import Catalog, now_iso

KIND_LABELS_FA = {
    "book": "کتاب و مقاله (pdf، epub …)", "document": "سند (Word، Excel، PowerPoint …)", "web": "صفحهٔ وب",
    "audio": "صوت", "video": "ویدیو", "image": "تصویر", "archive": "فایل فشرده", "software": "نرم‌افزار",
    "font": "فونت", "junk": "زائد/موقت", "other": "سایر",
}


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def write_text(path: Path, text: str) -> None:
    """Atomic write: a reader never sees a half-written report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    count = 0
    with open(temp, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
            count += 1
    os.replace(temp, path)
    return count


def _fmt_time(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):  # bogus dates from old FAT media, Windows epoch limits
        return ""


def _md_table(header: Sequence[str], rows: List[Sequence]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return "\n".join(lines)


def _header(title: str) -> str:
    return f"# {title}\n\nتولید شده با `versline organize` در {now_iso()}\n\n"


def write_stats(catalog: Catalog, reports_dir: Optional[Path] = None) -> Path:
    reports_dir = reports_dir or catalog.workspace / "reports"
    conn = catalog.conn
    parts = [_header("آمار کلی آرشیو")]

    root_rows = []
    for root in catalog.roots():
        count, size = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size),0) FROM files WHERE root_id=? AND present=1", (root["id"],)
        ).fetchone()
        missing = conn.execute("SELECT COUNT(*) FROM files WHERE root_id=? AND present=0", (root["id"],)).fetchone()[0]
        root_rows.append((root["label"], f"`{root['path']}`", f"{count:,}", human_size(size), missing,
                          root["last_scan_finished"] or "ناتمام"))
    parts.append("## منابع\n\n" + _md_table(
        ["منبع", "مسیر (نسبت به ریشهٔ درایو)", "تعداد فایل", "حجم", "ناپدیدشده از اسکن قبلی", "آخرین اسکن"],
        root_rows) + "\n")

    total_count, total_size = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(size),0) FROM files WHERE present=1").fetchone()
    parts.append(f"**جمع:** {total_count:,} فایل، {human_size(total_size)}\n")

    kind_rows = [
        (KIND_LABELS_FA.get(kind, kind), f"{count:,}", human_size(size), f"{100 * size / total_size:.1f}%" if total_size else "-")
        for kind, count, size in conn.execute(
            "SELECT kind, COUNT(*), SUM(size) s FROM files WHERE present=1 GROUP BY kind ORDER BY s DESC")
    ]
    parts.append("## بر اساس نوع\n\n" + _md_table(["نوع", "تعداد", "حجم", "سهم از حجم"], kind_rows) + "\n")

    per_root_kind = []
    for root in catalog.roots():
        cells = [root["label"]]
        for kind in ("book", "document", "audio", "video", "image", "software", "archive"):
            size = conn.execute("SELECT COALESCE(SUM(size),0) FROM files WHERE root_id=? AND kind=? AND present=1",
                                (root["id"], kind)).fetchone()[0]
            cells.append(human_size(size))
        per_root_kind.append(cells)
    parts.append("## حجم هر نوع در هر منبع\n\n" + _md_table(
        ["منبع", "کتاب", "سند", "صوت", "ویدیو", "تصویر", "نرم‌افزار", "فشرده"], per_root_kind) + "\n")

    ext_rows = [
        (ext or "(بدون پسوند)", kind, f"{count:,}", human_size(size))
        for ext, kind, count, size in conn.execute(
            "SELECT ext, kind, COUNT(*), SUM(size) s FROM files WHERE present=1 GROUP BY ext ORDER BY s DESC LIMIT 40")
    ]
    parts.append("## ۴۰ پسوند پرحجم\n\n" + _md_table(["پسوند", "نوع", "تعداد", "حجم"], ext_rows) + "\n")

    special = {}
    for dir_kind, file_name in (("scan_folder", "scan_folders.csv"), ("software", "software_folders.csv")):
        rows = conn.execute(
            "SELECT r.label, d.relpath, d.file_count, d.image_count, d.exe_count, d.direct_size FROM dirs d "
            "JOIN roots r ON r.id=d.root_id WHERE d.dir_kind=? ORDER BY r.label, d.relpath", (dir_kind,)).fetchall()
        write_csv(reports_dir / file_name, ["root", "folder", "files", "images", "executables", "size_bytes", "size"],
                  [(r[0], r[1], r[2], r[3], r[4], r[5], human_size(r[5])) for r in rows])
        special[dir_kind] = (len(rows), sum(r[5] for r in rows))
    parts.append(
        "## پوشه‌های یکپارچه (نباید از هم پاشیده شوند)\n\n"
        f"- **پوشهٔ اسکن کتاب** (≥۱۰ تصویر و ≥۸۰٪ فایل‌ها تصویر): {special['scan_folder'][0]:,} پوشه، "
        f"{human_size(special['scan_folder'][1])}؛ فهرست: `reports/scan_folders.csv`\n"
        f"- **پوشهٔ نرم‌افزار** (≥۵ فایل اجرایی و ≥۳۰٪): {special['software'][0]:,} پوشه، "
        f"{human_size(special['software'][1])}؛ فهرست: `reports/software_folders.csv`\n")

    error_rows = conn.execute(
        "SELECT COALESCE(r.label,''), e.relpath, e.stage, e.error, e.at FROM scan_errors e "
        "LEFT JOIN roots r ON r.id=e.root_id ORDER BY e.id").fetchall()
    write_csv(reports_dir / "scan_errors.csv", ["root", "path", "stage", "error", "at"], error_rows)
    parts.append(f"## خطاها\n\n{len(error_rows):,} خطا در خواندن (جزئیات: `reports/scan_errors.csv`).\n")

    hashed = conn.execute("SELECT COUNT(*) FROM files WHERE present=1 AND full_hash IS NOT NULL").fetchone()[0]
    parts.append(f"## hash\n\n{hashed:,} فایل hash کامل (SHA-256) دارند. "
                 "hash فقط برای فایل‌های هم‌اندازه حساب می‌شود (`versline organize dupes`).\n")

    path = reports_dir / "stats.md"
    write_text(path, "\n".join(parts))
    return path


def write_duplicates(catalog: Catalog, groups: List[dict], folders: List[dict],
                     reports_dir: Optional[Path] = None) -> Path:
    reports_dir = reports_dir or catalog.workspace / "reports"
    rows = []
    for index, group in enumerate(groups, 1):
        copies = len(group["members"])
        for file_id, label, relpath, kind in group["members"]:
            rows.append((index, group["size"], human_size(group["size"]), copies,
                         group["size"] * (copies - 1), label, relpath, kind, group["hash"]))
    write_csv(reports_dir / "duplicates.csv",
              ["group", "size_bytes", "size", "copies", "wasted_bytes", "root", "path", "kind", "sha256"], rows)
    write_csv(reports_dir / "redundant_folders.csv",
              ["folder", "files", "total_bytes", "total", "redundant_bytes", "ratio", "most_copies_in"],
              [(f["folder"], f["files"], f["total_bytes"], human_size(f["total_bytes"]), f["redundant_bytes"],
                f"{f['ratio']:.3f}", f["elsewhere"]) for f in folders])

    wasted = sum(g["size"] * (len(g["members"]) - 1) for g in groups)
    files = sum(len(g["members"]) for g in groups)
    by_kind = {}
    for group in groups:
        kind = group["members"][0][3]
        entry = by_kind.setdefault(kind, [0, 0])
        entry[0] += 1
        entry[1] += group["size"] * (len(group["members"]) - 1)

    parts = [_header("گزارش فایل‌های تکراری")]
    parts.append(
        f"- **{len(groups):,}** گروه فایل یکسان (بر اساس SHA-256 کامل)، شامل **{files:,}** فایل\n"
        f"- حجمی که با نگه‌داشتن فقط یک نسخه از هر گروه آزاد می‌شود: **{human_size(wasted)}**\n"
        "- هیچ فایلی حذف نشده است؛ این فقط گزارش است. فهرست کامل: `reports/duplicates.csv`\n")
    parts.append("## بر اساس نوع\n\n" + _md_table(
        ["نوع", "گروه", "حجم اضافه"],
        [(KIND_LABELS_FA.get(k, k), f"{v[0]:,}", human_size(v[1]))
         for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1][1])]) + "\n")
    parts.append(
        "## پوشه‌هایی که تقریباً کامل جای دیگری هم هستند\n\n"
        "پوشه‌هایی که دست‌کم ۹۰٪ حجمشان نسخهٔ یکسانی بیرون از خودشان دارد (فقط بالاترین سطح). "
        "دو پوشه که کپی هم باشند هر دو در فهرست می‌آیند؛ تصمیم نگه‌داشتن با شماست. "
        "فهرست کامل: `reports/redundant_folders.csv`\n\n" + _md_table(
            ["پوشه", "فایل", "حجم", "تکراری", "بیشتر نسخه‌ها در"],
            [(f["folder"], f"{f['files']:,}", human_size(f["total_bytes"]), f"{100 * f['ratio']:.0f}%", f["elsewhere"])
             for f in folders[:40]]) + "\n")
    parts.append("## ۳۰ گروه پرحجم\n\n" + _md_table(
        ["#", "حجم", "نسخه", "نمونه‌ها"],
        [(i, human_size(g["size"]), len(g["members"]),
          "<br>".join(f"{m[1]}/{m[2]}" for m in g["members"][:4]) + (" …" if len(g["members"]) > 4 else ""))
         for i, g in enumerate(groups[:30], 1)]) + "\n")

    path = reports_dir / "duplicates.md"
    write_text(path, "\n".join(parts))
    return path


def export_files(catalog: Catalog, reports_dir: Optional[Path] = None) -> Path:
    reports_dir = reports_dir or catalog.workspace / "reports"
    conn = catalog.conn
    counts = dict(conn.execute(
        "SELECT full_hash, COUNT(*) FROM files WHERE present=1 AND full_hash IS NOT NULL GROUP BY full_hash"))

    def rows():
        for label, relpath, name, ext, kind, size, mtime, digest in conn.execute(
            "SELECT r.label, f.relpath, f.name, f.ext, f.kind, f.size, f.mtime, f.full_hash FROM files f "
            "JOIN roots r ON r.id=f.root_id WHERE f.present=1 ORDER BY r.label, f.relpath"
        ):
            yield (label, relpath, name, ext, kind, size, human_size(size), _fmt_time(mtime),
                   digest or "", counts.get(digest, 1) if digest else 1)

    path = reports_dir / "files.csv"
    write_csv(path, ["root", "path", "name", "ext", "kind", "size_bytes", "size", "modified", "sha256", "copies"],
              rows())
    return path
