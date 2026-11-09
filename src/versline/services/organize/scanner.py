"""Incremental, read-only scan of source folders into the catalog."""
from __future__ import annotations

import os
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional

from loguru import logger

from versline.services.organize.catalog import Catalog, now_iso
from versline.services.organize.kinds import SOFTWARE_EXTS, classify_kind, file_ext
from versline.services.organize.normalize import fs_path, norm_name

MTIME_TOLERANCE = 2.0  # seconds; NTFS, FAT/exFAT and FUSE report modification times with different precision
COMMIT_EVERY = 2000
SKIP_DIR_NAMES = {"$recycle.bin", "$recycler", "recycler", "system volume information", "$windows.~bt",
                  "$windows.~ws", "found.000", "lost+found"}

SCAN_FOLDER_MIN_IMAGES = 10
SCAN_FOLDER_IMAGE_RATIO = 0.8
SOFTWARE_MIN_FILES = 5
SOFTWARE_RATIO = 0.3


@dataclass
class ScanResult:
    files: int = 0
    bytes: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    missing: int = 0
    errors: int = 0
    roots: List[str] = field(default_factory=list)


def _skip_dir(name: str) -> bool:
    low = name.lower()
    return low in SKIP_DIR_NAMES or low.startswith(".trash-")


def scan_sources(
    catalog: Catalog,
    sources: Iterable,
    progress: Optional[Callable[[ScanResult, str], None]] = None,
) -> ScanResult:
    """Walk every source folder and upsert its files. Never writes inside the sources."""
    result = ScanResult()
    workspace_n = os.path.normcase(str(catalog.workspace))
    for source in sources:
        if not os.path.isdir(fs_path(source)):
            raise NotADirectoryError(f"Source folder not found: {source}")
        root_id, label = catalog.add_root(source)
        result.roots.append(label)
        _scan_root(catalog, root_id, label, catalog.root_path(root_id), workspace_n, result, progress)
    return result


def _scan_root(catalog: Catalog, root_id: int, label: str, root_dir, workspace_n: str,
               result: ScanResult, progress) -> None:
    conn = catalog.conn
    started = now_iso()
    # A unique token per scan run marks the files seen in this run (two runs may start in the same second).
    token = f"{started}#{uuid.uuid4().hex[:8]}"
    conn.execute("UPDATE roots SET last_scan_started=? WHERE id=?", (started, root_id))
    conn.execute("DELETE FROM scan_errors WHERE root_id=? AND stage='scan'", (root_id,))  # re-detected below
    existing: Dict[str, tuple] = {
        row[0]: (row[1], row[2], row[3])
        for row in conn.execute("SELECT relpath, id, size, mtime FROM files WHERE root_id=?", (root_id,))
    }
    logger.info(f"Scanning '{label}' ({root_dir}); {len(existing)} files already in catalog")

    pending = 0
    unchanged_ids: List[tuple] = []
    stack = [""]
    while stack:
        rel = stack.pop()
        folder = root_dir.joinpath(*rel.split("/")) if rel else root_dir
        try:
            with os.scandir(fs_path(folder)) as iterator:
                entries = list(iterator)
        except OSError as exc:
            catalog.add_error(root_id, rel, "scan", f"{type(exc).__name__}: {exc}")
            result.errors += 1
            continue
        for entry in entries:
            name = entry.name
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                catalog.add_error(root_id, rel, "scan", f"undecodable file name: {name!r}")
                result.errors += 1
                continue
            child = f"{rel}/{name}" if rel else name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if _skip_dir(name) or os.path.normcase(os.path.abspath(str(folder / name))) == workspace_n:
                        continue
                    stack.append(child)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                catalog.add_error(root_id, child, "scan", f"{type(exc).__name__}: {exc}")
                result.errors += 1
                continue

            size, mtime = stat.st_size, float(stat.st_mtime)
            result.files += 1
            result.bytes += size
            previous = existing.get(child)
            if previous is None:
                conn.execute(
                    "INSERT INTO files(root_id, relpath, name, norm_name, ext, size, mtime, kind, present, last_seen)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (root_id, child, name, norm_name(name), file_ext(name), size, mtime, classify_kind(name), token),
                )
                result.new += 1
            elif previous[1] == size and abs(previous[2] - mtime) <= MTIME_TOLERANCE:
                unchanged_ids.append((token, previous[0]))
                result.unchanged += 1
            else:
                conn.execute(
                    "UPDATE files SET size=?, mtime=?, kind=?, partial_hash=NULL, full_hash=NULL, hash_size=NULL,"
                    " hash_mtime=NULL, present=1, last_seen=? WHERE id=?",
                    (size, mtime, classify_kind(name), token, previous[0]),
                )
                result.changed += 1
            pending += 1
            if pending >= COMMIT_EVERY:
                _flush(conn, unchanged_ids)
                pending = 0
                if progress:
                    progress(result, child)
    _flush(conn, unchanged_ids)

    cursor = conn.execute(
        "UPDATE files SET present=0 WHERE root_id=? AND (last_seen IS NULL OR last_seen<>?) AND present=1",
        (root_id, token),
    )
    result.missing += cursor.rowcount
    conn.execute("UPDATE roots SET last_scan_finished=? WHERE id=?", (now_iso(), root_id))
    conn.commit()
    rebuild_dirs(catalog, root_id)
    if progress:
        progress(result, "")


def _flush(conn, unchanged_ids: List[tuple]) -> None:
    if unchanged_ids:
        conn.executemany("UPDATE files SET present=1, last_seen=? WHERE id=?", unchanged_ids)
        unchanged_ids.clear()
    conn.commit()


def rebuild_dirs(catalog: Catalog, root_id: int) -> None:
    """Recompute per-folder statistics and detect scanned-book and software folders."""
    conn = catalog.conn
    direct = defaultdict(lambda: {"files": 0, "size": 0, "images": 0, "exes": 0, "kinds": Counter()})
    totals = defaultdict(lambda: [0, 0])
    for relpath, size, kind, ext in conn.execute(
        "SELECT relpath, size, kind, ext FROM files WHERE root_id=? AND present=1", (root_id,)
    ):
        parent = relpath.rpartition("/")[0]
        info = direct[parent]
        info["files"] += 1
        info["size"] += size
        info["kinds"][kind] += size
        if kind == "image":
            info["images"] += 1
        if ext in SOFTWARE_EXTS:
            info["exes"] += 1
        ancestor = parent
        while True:
            totals[ancestor][0] += 1
            totals[ancestor][1] += size
            if not ancestor:
                break
            ancestor = ancestor.rpartition("/")[0]

    rows = []
    for relpath, (total_files, total_size) in totals.items():
        info = direct.get(relpath, {"files": 0, "size": 0, "images": 0, "exes": 0, "kinds": Counter()})
        count = info["files"]
        dir_kind = None
        if info["images"] >= SCAN_FOLDER_MIN_IMAGES and info["images"] >= SCAN_FOLDER_IMAGE_RATIO * count:
            dir_kind = "scan_folder"
        elif info["exes"] >= SOFTWARE_MIN_FILES and info["exes"] >= SOFTWARE_RATIO * count:
            dir_kind = "software"
        dominant = info["kinds"].most_common(1)[0][0] if info["kinds"] else None
        rows.append((root_id, relpath, count, info["size"], total_files, total_size,
                     info["images"], info["exes"], dominant, dir_kind))
    conn.execute("DELETE FROM dirs WHERE root_id=?", (root_id,))
    conn.executemany(
        "INSERT INTO dirs(root_id, relpath, file_count, direct_size, total_files, total_size, image_count,"
        " exe_count, dominant_kind, dir_kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
