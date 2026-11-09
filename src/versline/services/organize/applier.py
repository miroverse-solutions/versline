"""Execute an approved plan: copy (verified with SHA-256) or move (same-drive rename), resumable and reversible.

Safety rules:
* never overwrite an existing destination file; a different file already there is reported as a conflict;
* never delete anything: a copy leaves the source in place, a move is a rename on the same drive;
* every move is journaled (``applied`` table + ``logs/moves.csv``) *before* it happens, so it can be reverted.
"""
from __future__ import annotations

import csv
import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from loguru import logger

from versline.services.organize.catalog import Catalog, now_iso
from versline.services.organize.hashing import CHUNK_BYTES, full_hash
from versline.services.organize.normalize import fs_path
from versline.services.organize.planner import COPY, MOVE, SKIP_DUP, SKIP_JUNK
from versline.services.organize.reports import _header, _md_table, human_size, write_csv, write_text

_APPLIED_SCHEMA = """
CREATE TABLE IF NOT EXISTS applied (
    key TEXT PRIMARY KEY,            -- '<root label>/<relpath>' of the source
    action TEXT NOT NULL, dest TEXT NOT NULL, size INTEGER, sha256 TEXT,
    status TEXT NOT NULL,            -- moving | done | error | reverted
    error TEXT, at TEXT
);
"""
FREE_SPACE_MARGIN = 2 * 1024 ** 3
COMMIT_SECONDS = 10.0


class ConflictError(Exception):
    pass


@dataclass
class ApplyResult:
    copied: int = 0
    moved: int = 0
    skipped: int = 0          # already done earlier, or not approved
    errors: int = 0
    bytes_copied: int = 0
    dry_run: bool = False


@dataclass
class ApplyProgress:
    done_files: int
    total_files: int
    done_bytes: int
    total_bytes: int
    current: str


def ensure_applied_table(catalog: Catalog) -> None:
    catalog.conn.executescript(_APPLIED_SCHEMA)


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def _is_within(child: Path, parent: Path) -> bool:
    child_n, parent_n = os.path.normcase(os.path.abspath(str(child))), os.path.normcase(os.path.abspath(str(parent)))
    try:
        return os.path.commonpath([child_n, parent_n]) == parent_n
    except ValueError:
        return False


def check_destination(catalog: Catalog, dest_root: Path) -> None:
    for root in catalog.roots():
        source = catalog.root_path(root)
        if _is_within(dest_root, source) or _is_within(source, dest_root):
            raise ValueError(f"Destination {dest_root} overlaps source {source}; choose another @dest_root.")


def _copy_file(src: Path, dst: Path, expected: Optional[str], on_bytes) -> str:
    if os.path.exists(fs_path(dst)):
        # Accept an identical file (e.g. copied by an earlier, interrupted run); never overwrite anything else.
        if os.path.getsize(fs_path(dst)) == os.path.getsize(fs_path(src)):
            digest = full_hash(dst)
            if digest == (expected or full_hash(src)):
                return digest
        raise ConflictError(f"different file already at destination: {dst}")
    os.makedirs(fs_path(dst.parent), exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    digest = hashlib.sha256()
    with open(fs_path(src), "rb") as reader, open(fs_path(part), "wb") as writer:
        while True:
            block = reader.read(CHUNK_BYTES)
            if not block:
                break
            writer.write(block)
            digest.update(block)
            on_bytes(len(block))
    result = digest.hexdigest()
    if expected and result != expected:
        raise IOError(f"checksum mismatch while copying {src} (source changed since scan?)")
    try:
        stat = os.stat(fs_path(src))
        os.utime(fs_path(part), (stat.st_atime, stat.st_mtime))
    except OSError:
        pass
    os.rename(fs_path(part), fs_path(dst))
    return result


def _move_file(src: Path, dst: Path) -> None:
    src_exists, dst_exists = os.path.exists(fs_path(src)), os.path.exists(fs_path(dst))
    if dst_exists and not src_exists:
        return  # already moved (e.g. interrupted after the rename)
    if dst_exists:
        raise ConflictError(f"destination already exists: {dst}")
    if not src_exists:
        raise FileNotFoundError(f"source not found: {src}")
    os.makedirs(fs_path(dst.parent), exist_ok=True)
    if os.stat(fs_path(src)).st_dev != os.stat(fs_path(dst.parent)).st_dev:
        raise IOError("move needs source and destination on the same drive")
    os.rename(fs_path(src), fs_path(dst))


def _log_move(path: Path, src: str, dst: str, event: str) -> None:
    new = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["at", "event", "from", "to"])
        writer.writerow([now_iso(), event, src, dst])


def apply_plan(catalog: Catalog, plan: List[dict], dest_root: Path, only: Optional[str] = None,
               dry_run: bool = False, progress: Optional[Callable[[ApplyProgress], None]] = None,
               skip_unclassified: bool = False) -> ApplyResult:
    """``skip_unclassified`` leaves rows without a rule (going to the @default archive) for a later run."""
    ensure_applied_table(catalog)
    check_destination(catalog, dest_root)
    conn = catalog.conn
    roots = {r["label"]: catalog.root_path(r) for r in catalog.roots()}
    hashes = {f"{label}/{relpath}": digest for label, relpath, digest in conn.execute(
        "SELECT r.label, f.relpath, f.full_hash FROM files f JOIN roots r ON r.id=f.root_id WHERE f.full_hash IS NOT NULL")}
    state = {key: (status, dest) for key, status, dest in conn.execute("SELECT key, status, dest FROM applied")}

    actions = (only,) if only else (MOVE, COPY)  # moves first: instant, and they free the user's attention early
    todo = []
    result = ApplyResult(dry_run=dry_run)
    for action in actions:
        for row in plan:
            if row["action"] != action:
                continue
            key = f"{row['root']}/{row['path']}"
            if row["approved"] not in ("yes", "y", "1", "true", "بله") or (
                    skip_unclassified and row.get("rule") == "default"):
                result.skipped += 1
                continue
            if state.get(key, ("",))[0] == "done":
                result.skipped += 1
                continue
            todo.append(row)

    copy_bytes = sum(r["size"] for r in todo if r["action"] == COPY)
    if dry_run:
        result.copied = sum(1 for r in todo if r["action"] == COPY)
        result.moved = sum(1 for r in todo if r["action"] == MOVE)
        result.bytes_copied = copy_bytes
        return result
    dest_root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(str(dest_root)).free
    if copy_bytes + FREE_SPACE_MARGIN > free:
        raise OSError(f"Not enough free space: copies need {human_size(copy_bytes)} (+2 GB margin), "
                      f"{human_size(free)} free.")

    moves_log = catalog.workspace / "logs" / "moves.csv"
    status = ApplyProgress(0, len(todo), 0, copy_bytes, "")
    last_commit = time.monotonic()

    def bump(count: int) -> None:
        status.done_bytes += count
        if progress:
            progress(status)

    try:
        for row in todo:
            key = f"{row['root']}/{row['path']}"
            src = roots[row["root"]].joinpath(*row["path"].split("/"))
            dst = dest_root.joinpath(*row["dest"].split("/"))
            status.current = row["dest"]
            try:
                if row["action"] == MOVE:
                    conn.execute("INSERT OR REPLACE INTO applied(key, action, dest, size, status, at) "
                                 "VALUES (?, ?, ?, ?, 'moving', ?)", (key, MOVE, row["dest"], row["size"], now_iso()))
                    conn.commit()  # journal the intent before touching the file
                    _move_file(src, dst)
                    conn.execute("UPDATE applied SET status='done', at=? WHERE key=?", (now_iso(), key))
                    conn.commit()
                    _log_move(moves_log, str(src), str(dst), "move")
                    result.moved += 1
                else:
                    digest = _copy_file(src, dst, hashes.get(key), bump)
                    conn.execute("INSERT OR REPLACE INTO applied(key, action, dest, size, sha256, status, at) "
                                 "VALUES (?, ?, ?, ?, ?, 'done', ?)", (key, COPY, row["dest"], row["size"], digest, now_iso()))
                    result.copied += 1
                    result.bytes_copied += row["size"]
            except (OSError, ConflictError) as exc:
                result.errors += 1
                logger.warning(f"{row['action']} failed for {key}: {exc}")
                conn.execute("INSERT OR REPLACE INTO applied(key, action, dest, size, status, error, at) "
                             "VALUES (?, ?, ?, ?, 'error', ?, ?)", (key, row["action"], row["dest"], row["size"],
                                                                     f"{type(exc).__name__}: {exc}"[:500], now_iso()))
            status.done_files += 1
            if progress:
                progress(status)
            if time.monotonic() - last_commit > COMMIT_SECONDS:
                conn.commit()
                last_commit = time.monotonic()
    finally:
        conn.commit()
    return result


def revert_moves(catalog: Catalog, dest_root: Path, dry_run: bool = False) -> Dict[str, int]:
    """Move every applied move back to its original place (newest first). Copies are left alone."""
    ensure_applied_table(catalog)
    conn = catalog.conn
    roots = {r["label"]: catalog.root_path(r) for r in catalog.roots()}
    counts = {"reverted": 0, "skipped": 0, "errors": 0}
    rows = conn.execute("SELECT key, dest FROM applied WHERE action='move' AND status IN ('done','moving') "
                        "ORDER BY at DESC").fetchall()
    for key, dest in rows:
        label, _, relpath = key.partition("/")
        src = roots[label].joinpath(*relpath.split("/"))
        dst = dest_root.joinpath(*dest.split("/"))
        if not os.path.exists(fs_path(dst)) or os.path.exists(fs_path(src)):
            counts["skipped"] += 1
            continue
        if dry_run:
            counts["reverted"] += 1
            continue
        try:
            os.makedirs(fs_path(src.parent), exist_ok=True)
            os.rename(fs_path(dst), fs_path(src))
            conn.execute("UPDATE applied SET status='reverted', at=? WHERE key=?", (now_iso(), key))
            conn.commit()
            _log_move(catalog.workspace / "logs" / "moves.csv", str(dst), str(src), "revert")
            counts["reverted"] += 1
        except OSError as exc:
            counts["errors"] += 1
            logger.warning(f"revert failed for {key}: {exc}")
    return counts


def verify(catalog: Catalog, plan: List[dict], dest_root: Path, deep: bool = False,
           reports_dir: Optional[Path] = None) -> Dict[str, int]:
    """Coverage report: every catalogued file must be copied, moved, deliberately skipped, or reported."""
    ensure_applied_table(catalog)
    reports_dir = reports_dir or catalog.workspace / "reports"
    roots = {r["label"]: catalog.root_path(r) for r in catalog.roots()}
    applied = {key: (status, sha) for key, status, sha in catalog.conn.execute("SELECT key, status, sha256 FROM applied")}
    dest_exists_cache: Dict[str, bool] = {}

    def exists(rel: str) -> bool:
        if rel not in dest_exists_cache:
            dest_exists_cache[rel] = os.path.exists(fs_path(dest_root.joinpath(*rel.split("/"))))
        return dest_exists_cache[rel]

    counts: Dict[str, int] = {}
    out = []
    for row in plan:
        key = f"{row['root']}/{row['path']}"
        approved = row["approved"] in ("yes", "y", "1", "true", "بله")
        action = row["action"]
        if action == SKIP_JUNK:
            state = "skipped_junk"
        elif not approved:
            state = "excluded_by_user"
        elif action == SKIP_DUP:
            state = "duplicate_ok" if exists(row["duplicate_of"]) else "duplicate_keeper_missing"
        else:
            status, sha = applied.get(key, ("", None))
            dst = dest_root.joinpath(*row["dest"].split("/"))
            if status == "error":
                state = "error"
            elif status != "done":
                state = "pending"
            elif not exists(row["dest"]):
                state = "MISSING_AT_DESTINATION"
            elif os.path.getsize(fs_path(dst)) != row["size"]:
                state = "SIZE_MISMATCH"
            elif action == MOVE and os.path.exists(fs_path(roots[row["root"]].joinpath(*row["path"].split("/")))):
                state = "moved_but_source_still_exists"
            elif deep and action == COPY and sha and full_hash(dst) != sha:
                state = "HASH_MISMATCH"
            else:
                state = "copied" if action == COPY else "moved"
        counts[state] = counts.get(state, 0) + 1
        out.append((state, action, row["root"], row["path"], row["dest"], row["size"]))

    write_csv(reports_dir / "coverage.csv", ["state", "action", "root", "path", "dest", "size"], out)
    ok = {"copied", "moved", "skipped_junk", "duplicate_ok", "excluded_by_user"}
    problems = [r for r in out if r[0] not in ok]
    parts = [_header("گزارش تطبیق و پوشش")]
    parts.append(_md_table(["وضعیت", "تعداد"], [(k, f"{v:,}") for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]))
    parts.append("\n\n" + ("✅ همهٔ فایل‌ها تکلیفشان روشن است." if not problems else
                          f"⚠️ {len(problems):,} مورد نیاز به بررسی دارد (`pending` یعنی هنوز اجرا نشده). "
                          "جزئیات: `reports/coverage.csv`"))
    if problems:
        parts.append("\n\n" + _md_table(["وضعیت", "منبع", "مقصد"],
                                        [(p[0], f"{p[2]}/{p[3]}", p[4]) for p in problems[:50]]))
    write_text(reports_dir / "verify.md", "\n".join(parts) + "\n")
    return counts
