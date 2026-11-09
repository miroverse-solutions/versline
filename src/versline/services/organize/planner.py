"""Turn the catalog + rules into a reviewable plan (``plan/plan.csv``): what is copied, moved or skipped, and where to.

Nothing is written outside the workspace here; ``apply`` executes an approved plan.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from versline.services.organize.catalog import Catalog
from versline.services.organize.normalize import norm_name, split_ext, windows_safe_name
from versline.services.organize.reports import _header, _md_table, human_size, write_csv, write_text
from versline.services.organize.rules import RuleSet, outside_taxonomy

PLAN_HEADER = ["id", "approved", "action", "root", "path", "dest", "size", "kind", "rule", "note", "duplicate_of"]
LONG_PATH_LIMIT = 240

COPY, MOVE, SKIP_DUP, SKIP_JUNK = "copy", "move", "skip_duplicate", "skip_junk"


@dataclass
class PlanRow:
    id: int
    action: str
    root: str
    path: str
    dest: str
    size: int
    kind: str
    rule: str
    note: str = ""
    duplicate_of: str = ""
    approved: str = "yes"
    full_hash: Optional[str] = None
    keeper: Optional["PlanRow"] = field(default=None, repr=False)

    def as_csv(self) -> list:
        return [self.id, self.approved, self.action, self.root, self.path, self.dest, self.size, self.kind,
                self.rule, self.note, self.duplicate_of]


def _media_ratios(files, media_kinds) -> Dict[str, float]:
    """Share of audio/video bytes per folder (recursive), keyed by ``label/dir``."""
    totals: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for label, relpath, size, kind, _ in files:
        folder = label
        is_media = kind in media_kinds
        parts = relpath.split("/")[:-1]
        for part in [None] + parts:
            if part is not None:
                folder = f"{folder}/{part}"
            entry = totals[folder]
            entry[0] += size
            if is_media:
                entry[1] += size
    return {folder: (media / total if total else 0.0) for folder, (total, media) in totals.items()}


def _safe_dest(dest: str) -> str:
    return "/".join(windows_safe_name(part) for part in dest.split("/") if part)


def _with_suffix(dest: str, number: int) -> str:
    folder, _, name = dest.rpartition("/")
    stem, ext = split_ext(name)
    name = f"{stem} ({number}).{ext}" if ext else f"{stem} ({number})"
    return f"{folder}/{name}" if folder else name


def build_plan(catalog: Catalog, ruleset: RuleSet, taxonomy: Optional[List[str]] = None) -> Tuple[List[PlanRow], dict]:
    files = catalog.conn.execute(
        "SELECT r.label, f.relpath, f.size, f.kind, f.full_hash FROM files f JOIN roots r ON r.id=f.root_id "
        "WHERE f.present=1 ORDER BY r.id, f.relpath").fetchall()
    media_kinds = set(ruleset.media_kinds)
    ratios = _media_ratios(files, media_kinds)

    rows: List[PlanRow] = []
    for index, (label, relpath, size, kind, digest) in enumerate(files, 1):
        assigned = ruleset.assignment(label, relpath)
        rule, rest = (None, "") if assigned else ruleset.match(label, relpath)
        if assigned:
            dest, rule_label = f"{assigned[0]}/{relpath.rsplit('/', 1)[-1]}", f"assign:{assigned[1]}"
        elif rule:
            dest, rule_label = f"{rule.dest}/{rest}", rule.label
        else:
            dest, rule_label = f"{ruleset.default}/{label}/{relpath}", "default"
        notes = []
        is_media = kind in media_kinds
        parent = f"{label}/{relpath.rpartition('/')[0]}".rstrip("/")
        if is_media:
            dest = ruleset.media_dest(dest)
        elif not assigned and ratios.get(parent, 0.0) >= ruleset.media_folder_ratio:  # an explicit assignment wins
            new_dest = ruleset.media_dest(dest)
            if new_dest != dest:
                notes.append("with-media")
                dest = new_dest
        action = SKIP_JUNK if kind == "junk" else (MOVE if is_media else COPY)
        rows.append(PlanRow(index, action, label, relpath, _safe_dest(dest), size, kind, rule_label,
                            " ".join(notes), full_hash=digest))

    _dedupe_copies(rows, ruleset)
    collisions = _resolve_collisions(rows, ruleset)
    for row in rows:
        if row.keeper is not None:
            row.duplicate_of = row.keeper.dest  # after collision renames, so it names the final destination

    warnings = Counter()
    full_root = len(ruleset.dest_root) + 1
    for row in rows:
        if row.action in (COPY, MOVE) and full_root + len(row.dest) + 3 > LONG_PATH_LIMIT:
            row.note = (row.note + " long-path").strip()
            warnings["long-path"] += 1
    off_taxonomy = sorted({"/".join(r.dest.split("/")[:2]) for r in rows
                           if r.action in (COPY, MOVE) and outside_taxonomy(r.dest, taxonomy or [])})
    stats = {"collisions": collisions, "long_paths": warnings["long-path"], "off_taxonomy": off_taxonomy}
    return rows, stats


def _dedupe_copies(rows: List[PlanRow], ruleset: RuleSet) -> None:
    """Keep one copy per identical content; media is moved as-is so every course stays complete."""
    groups: Dict[str, List[PlanRow]] = defaultdict(list)
    for row in rows:
        if row.action == COPY and row.full_hash:
            groups[row.full_hash].append(row)
    default_prefix = _safe_dest(ruleset.default) + "/"
    for members in groups.values():
        if len(members) < 2:
            continue
        keeper = min(members, key=lambda r: (r.dest.startswith(default_prefix), ruleset.priority(r.root),
                                             r.path.count("/"), len(r.path), r.path))
        for row in members:
            if row is not keeper:
                row.action = SKIP_DUP
                row.keeper = keeper


def _resolve_collisions(rows: List[PlanRow], ruleset: RuleSet) -> int:
    """Different files mapped to the same destination get ``name (2).ext``; nothing is ever overwritten.
    The copy from the higher-priority source keeps the plain name."""
    taken = set()
    collisions = 0
    for row in sorted(rows, key=lambda r: (ruleset.priority(r.root), r.id)):
        if row.action not in (COPY, MOVE):
            continue
        key = norm_name(row.dest)
        if key in taken:
            number = 2
            while norm_name(_with_suffix(row.dest, number)) in taken:
                number += 1
            row.dest = _with_suffix(row.dest, number)
            row.note = (row.note + " renamed-collision").strip()  # same name, different content
            key = norm_name(row.dest)
            collisions += 1
        taken.add(key)
    return collisions


def write_plan(rows: List[PlanRow], path: Path) -> None:
    write_csv(path, PLAN_HEADER, (row.as_csv() for row in rows))


def write_plan_summary(rows: List[PlanRow], stats: dict, ruleset: RuleSet, path: Path) -> None:
    def tally(items):
        result: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
        for key, size in items:
            result[key][0] += 1
            result[key][1] += size
        return result

    parts = [_header("برنامهٔ سازمان‌دهی (پیش‌نویس برای بازبینی)")]
    parts.append(
        f"مقصد: `{ruleset.dest_root}/` در ریشهٔ درایو. **هنوز هیچ کاری انجام نشده است**؛ اجرا فقط با "
        "`versline organize apply` و پس از تأیید شما.\n\n"
        "- **move** (صوت و ویدیو): جابه‌جایی روی همان درایو، آنی. هر جابه‌جایی در `logs/moves.csv` ثبت می‌شود و با "
        "`versline organize revert-moves` برمی‌گردد.\n"
        "- **copy** (بقیه): نسخهٔ اصلی سر جایش می‌ماند؛ کپی با SHA-256 تطبیق داده می‌شود.\n"
        "- **skip_duplicate**: نسخهٔ یکسانش جای دیگری کپی می‌شود (ستون `duplicate_of`).\n"
        "- **skip_junk**: فایل‌های موقت و زائد (Thumbs.db، ~$…، .tmp).\n")
    by_action = tally((r.action, r.size) for r in rows)
    parts.append("## خلاصه\n\n" + _md_table(
        ["اقدام", "فایل", "حجم"],
        [(a, f"{v[0]:,}", human_size(v[1])) for a, v in sorted(by_action.items(), key=lambda kv: -kv[1][1])]) + "\n")

    by_dest = tally(("/".join(r.dest.split("/")[:-1][:2]), r.size) for r in rows if r.action in (COPY, MOVE))
    parts.append("## مقصدها (دو سطح اول)\n\n" + _md_table(
        ["پوشهٔ مقصد", "فایل", "حجم"],
        [(f"`{k}`", f"{v[0]:,}", human_size(v[1])) for k, v in sorted(by_dest.items())]) + "\n")

    by_rule: Dict[str, List] = {}
    for row in rows:
        if row.action not in (COPY, MOVE):
            continue
        entry = by_rule.setdefault(row.rule, [0, 0, 0, 0])
        entry[0] += 1
        entry[1] += row.size
        entry[2 if row.action == MOVE else 3] += 1
    rule_dest = {r.label: r.dest for r in ruleset.rules}
    rule_dest.update({f"assign:{by}": "(assignments.csv)" for _, by in ruleset.assignments.values()})
    parts.append("## بر اساس قاعده\n\n" + _md_table(
        ["قاعده (شماره خط: منبع)", "مقصد", "فایل", "حجم", "move", "copy"],
        [(k, rule_dest.get(k, ruleset.default), f"{v[0]:,}", human_size(v[1]), f"{v[2]:,}", f"{v[3]:,}")
         for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1][1])]) + "\n")

    unmatched = tally(("/".join([r.root] + r.path.split("/")[:-1][:2]), r.size)
                      for r in rows if r.rule == "default" and r.action in (COPY, MOVE))
    parts.append(
        "## بدون قاعده (می‌روند به بایگانی خام)\n\n"
        "برای این‌ها قاعده بنویسید یا بگذارید در «بایگانی خام» بمانند. پرحجم‌ترین پوشه‌ها:\n\n" + _md_table(
            ["پوشهٔ منبع", "فایل", "حجم"],
            [(k, f"{v[0]:,}", human_size(v[1])) for k, v in sorted(unmatched.items(), key=lambda kv: -kv[1][1])[:60]])
        + "\n")

    warn = [f"- نام‌های تکراری در مقصد که با ` (2)` تغییر نام یافتند: {stats['collisions']:,}",
            f"- مسیرهای بلندتر از {LONG_PATH_LIMIT} نویسه (در ویندوز ممکن است دردسر شوند): {stats['long_paths']:,}"]
    if stats["off_taxonomy"]:
        warn.append("- مقصدهایی بیرون از `taxonomy.txt`: " + "، ".join(f"`{d}`" for d in stats["off_taxonomy"]))
    parts.append("## هشدارها\n\n" + "\n".join(warn) + "\n")
    write_text(path, "\n".join(parts))


def read_plan(path: Path) -> List[dict]:
    """Read a (possibly Excel-edited) plan.csv. Excel must save it as 'CSV UTF-8'."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in PLAN_HEADER if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{path}: missing columns {missing}")
            rows = list(reader)
    except UnicodeDecodeError:
        raise ValueError(f"{path} is not UTF-8. In Excel use 'Save As → CSV UTF-8 (Comma delimited)'.")
    for row in rows:
        row["size"] = int(row["size"] or 0)
        row["approved"] = (row.get("approved") or "").strip().lower()
    return rows
