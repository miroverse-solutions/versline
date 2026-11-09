"""Duplicate detection: size → partial hash → full SHA-256, with every hash saved as soon as it is computed."""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from loguru import logger

from versline.services.organize.catalog import Catalog
from versline.services.organize.hashing import PARTIAL_BYTES, full_hash, partial_hash

COMMIT_SECONDS = 15.0


@dataclass
class HashProgress:
    stage: str            # "partial" or "full"
    done_files: int
    total_files: int
    done_bytes: int
    total_bytes: int


@dataclass
class DupeSummary:
    groups: int
    files: int
    wasted_bytes: int
    errors: int


def _hash_files(catalog: Catalog, rows, stage: str, progress) -> int:
    """Compute hashes for ``rows`` (id, root_id, relpath, size, mtime); returns the error count."""
    conn = catalog.conn
    total_files = len(rows)
    total_bytes = sum(row[3] if stage == "full" else min(row[3], 2 * PARTIAL_BYTES) for row in rows)
    state = HashProgress(stage, 0, total_files, 0, total_bytes)
    errors = 0
    last_commit = time.monotonic()

    def bump(count: int) -> None:
        state.done_bytes += count
        if progress:
            progress(state)

    for file_id, root_id, relpath, size, mtime in rows:
        path = catalog.file_path(root_id, relpath)
        try:
            if stage == "partial" and size > 2 * PARTIAL_BYTES:
                conn.execute(
                    "UPDATE files SET partial_hash=?, hash_size=?, hash_mtime=? WHERE id=?",
                    (partial_hash(path, size), size, mtime, file_id),
                )
                bump(2 * PARTIAL_BYTES)
            else:
                # Small files are read whole anyway, so their partial hash *is* the full hash.
                digest = full_hash(path, on_bytes=bump if stage == "full" else None)
                if stage == "partial":
                    bump(size)
                conn.execute(
                    "UPDATE files SET partial_hash=?, full_hash=?, hash_size=?, hash_mtime=? WHERE id=?",
                    (digest, digest, size, mtime, file_id),
                )
        except OSError as exc:
            errors += 1
            catalog.add_error(root_id, relpath, f"hash-{stage}", f"{type(exc).__name__}: {exc}")
            logger.warning(f"Could not read {path}: {exc}")
        state.done_files += 1
        if progress:
            progress(state)
        if time.monotonic() - last_commit > COMMIT_SECONDS:
            conn.commit()
            last_commit = time.monotonic()
    conn.commit()
    return errors


def find_duplicates(catalog: Catalog, min_size: int = 1,
                    progress: Optional[Callable[[HashProgress], None]] = None) -> DupeSummary:
    """Hash only what is needed to prove which files are identical. Safe to interrupt and rerun."""
    conn = catalog.conn
    min_size = max(1, int(min_size))
    # Files that failed before still have no hash, so they are retried below; drop their stale errors.
    conn.execute("DELETE FROM scan_errors WHERE stage LIKE 'hash-%'")
    conn.execute("DROP TABLE IF EXISTS temp.cand_sizes")
    conn.execute(
        "CREATE TEMP TABLE cand_sizes AS SELECT size FROM files WHERE present=1 AND size>=? "
        "GROUP BY size HAVING COUNT(*)>1",
        (min_size,),
    )
    rows = conn.execute(
        "SELECT id, root_id, relpath, size, mtime FROM files WHERE present=1 AND partial_hash IS NULL "
        "AND size IN (SELECT size FROM temp.cand_sizes) ORDER BY root_id, relpath"
    ).fetchall()
    logger.info(f"Partial hashing {len(rows)} same-size candidates")
    errors = _hash_files(catalog, [tuple(r) for r in rows], "partial", progress)

    rows = conn.execute(
        "SELECT f.id, f.root_id, f.relpath, f.size, f.mtime FROM files f JOIN ("
        "  SELECT size, partial_hash FROM files WHERE present=1 AND partial_hash IS NOT NULL AND size>=? "
        "  GROUP BY size, partial_hash HAVING COUNT(*)>1"
        ") g ON f.size=g.size AND f.partial_hash=g.partial_hash "
        "WHERE f.present=1 AND f.full_hash IS NULL ORDER BY f.root_id, f.relpath",
        (min_size,),
    ).fetchall()
    logger.info(f"Full hashing {len(rows)} files ({sum(r[3] for r in rows) / 1e9:.1f} GB)")
    errors += _hash_files(catalog, [tuple(r) for r in rows], "full", progress)

    groups = duplicate_groups(catalog, min_size)
    files = sum(len(g["members"]) for g in groups)
    wasted = sum(g["size"] * (len(g["members"]) - 1) for g in groups)
    return DupeSummary(len(groups), files, wasted, errors)


def duplicate_groups(catalog: Catalog, min_size: int = 1) -> List[dict]:
    """Groups of identical present files, biggest waste first. Each member: (id, root_label, relpath, kind)."""
    groups: Dict[str, dict] = {}
    for file_id, label, relpath, kind, size, digest in catalog.conn.execute(
        "SELECT f.id, r.label, f.relpath, f.kind, f.size, f.full_hash FROM files f JOIN roots r ON r.id=f.root_id "
        "WHERE f.present=1 AND f.size>=? AND f.full_hash IN ("
        "  SELECT full_hash FROM files WHERE present=1 AND full_hash IS NOT NULL GROUP BY full_hash HAVING COUNT(*)>1"
        ") ORDER BY r.label, f.relpath",
        (max(1, int(min_size)),),
    ):
        group = groups.setdefault(digest, {"hash": digest, "size": size, "members": []})
        group["members"].append((file_id, label, relpath, kind))
    result = [g for g in groups.values() if len(g["members"]) > 1]
    result.sort(key=lambda g: g["size"] * (len(g["members"]) - 1), reverse=True)
    return result


def _ancestors(label: str, relpath: str) -> List[str]:
    """``["lib", "lib/a", "lib/a/b"]`` for file ``lib``/``a/b/file.pdf``."""
    parts = relpath.split("/")[:-1]
    result = [label]
    for part in parts:
        result.append(f"{result[-1]}/{part}")
    return result


def redundant_folders(catalog: Catalog, groups: List[dict], min_ratio: float = 0.9,
                      min_bytes: int = 1_000_000) -> List[dict]:
    """Folders whose content (by bytes) almost entirely also exists outside them.

    Only the top-most qualifying folder of a branch is returned.
    """
    totals: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for label, relpath, size in catalog.conn.execute(
        "SELECT r.label, f.relpath, f.size FROM files f JOIN roots r ON r.id=f.root_id WHERE f.present=1"
    ):
        for folder in _ancestors(label, relpath):
            totals[folder][0] += size
            totals[folder][1] += 1

    redundant: Dict[str, int] = defaultdict(int)
    elsewhere: Dict[str, Counter] = defaultdict(Counter)
    for group in groups:
        members = [(label, relpath) for _, label, relpath, _ in group["members"]]
        member_ancestors = [_ancestors(label, relpath) for label, relpath in members]
        member_sets = [set(a) for a in member_ancestors]
        under = Counter(folder for ancestors in member_ancestors for folder in ancestors)
        total = len(members)
        for index, ancestors in enumerate(member_ancestors):
            for folder in ancestors:
                if under[folder] >= total:
                    continue  # every copy is inside this folder: no copy elsewhere
                redundant[folder] += group["size"]
                for other_index, other_set in enumerate(member_sets):
                    if other_index != index and folder not in other_set:
                        elsewhere[folder][member_ancestors[other_index][-1]] += group["size"]
                        break

    candidates = []
    for folder, extra in redundant.items():
        total_bytes, total_files = totals.get(folder, (0, 0))
        if total_bytes >= min_bytes and total_bytes and extra / total_bytes >= min_ratio:
            candidates.append({
                "folder": folder, "total_bytes": total_bytes, "files": total_files,
                "redundant_bytes": extra, "ratio": extra / total_bytes,
                "elsewhere": elsewhere[folder].most_common(1)[0][0] if elsewhere[folder] else "",
            })
    candidates.sort(key=lambda c: c["folder"].count("/"))
    chosen: List[dict] = []
    chosen_names = set()
    for candidate in candidates:
        folder = candidate["folder"]
        parents = _ancestors(*folder.split("/", 1)) if "/" in folder else []
        if any(p in chosen_names for p in parents) or folder in chosen_names:
            continue
        chosen.append(candidate)
        chosen_names.add(folder)
    chosen.sort(key=lambda c: c["redundant_bytes"], reverse=True)
    return chosen
