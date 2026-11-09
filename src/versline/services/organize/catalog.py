"""SQLite catalog kept inside the workspace folder on the drive itself.

Root paths are stored relative to the workspace's parent folder (normally the drive root), so the
catalog keeps working when the drive gets another letter on Windows or another mount point on Linux.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

SCHEMA_VERSION = 1
WORKSPACE_DIRNAME = "_versline_organize"
CATALOG_NAME = "catalog.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS roots (
    id INTEGER PRIMARY KEY, label TEXT UNIQUE NOT NULL, path TEXT NOT NULL, is_relative INTEGER NOT NULL,
    last_scan_started TEXT, last_scan_finished TEXT
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL, relpath TEXT NOT NULL,
    name TEXT NOT NULL, norm_name TEXT NOT NULL, ext TEXT NOT NULL,
    size INTEGER NOT NULL, mtime REAL NOT NULL, kind TEXT NOT NULL,
    partial_hash TEXT, full_hash TEXT, hash_size INTEGER, hash_mtime REAL,
    present INTEGER NOT NULL DEFAULT 1, last_seen TEXT,
    UNIQUE (root_id, relpath)
);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_full_hash ON files(full_hash);
CREATE TABLE IF NOT EXISTS dirs (
    id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL, relpath TEXT NOT NULL,
    file_count INTEGER NOT NULL, direct_size INTEGER NOT NULL,
    total_files INTEGER NOT NULL, total_size INTEGER NOT NULL,
    image_count INTEGER NOT NULL, exe_count INTEGER NOT NULL,
    dominant_kind TEXT, dir_kind TEXT,
    UNIQUE (root_id, relpath)
);
CREATE TABLE IF NOT EXISTS scan_errors (
    id INTEGER PRIMARY KEY, root_id INTEGER, relpath TEXT, stage TEXT, error TEXT, at TEXT
);
"""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _is_within(child: str, parent: str) -> bool:
    child_n, parent_n = os.path.normcase(child), os.path.normcase(parent)
    try:
        return os.path.commonpath([child_n, parent_n]) == parent_n
    except ValueError:  # different drives on Windows
        return False


class Catalog:
    def __init__(self, workspace, create: bool = True):
        self.workspace = Path(os.path.abspath(str(workspace)))
        self.path = self.workspace / CATALOG_NAME
        if not create and not self.path.is_file():
            raise FileNotFoundError(f"No catalog found at {self.path}. Run 'versline organize scan' first.")
        self.workspace.mkdir(parents=True, exist_ok=True)
        for sub in ("reports", "logs"):
            (self.workspace / sub).mkdir(exist_ok=True)
        self.base = self.workspace.parent
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        # The catalog usually lives on an external NTFS/exFAT drive (sometimes behind FUSE or a sandbox that
        # forbids deleting files). A rollback journal that is truncated instead of deleted works on all of
        # them; WAL (shared memory) and DELETE (unlinks the journal after every commit) do not.
        self.conn.execute("PRAGMA journal_mode=TRUNCATE")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(_SCHEMA)
        if self.get_meta("schema_version") is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
            self.set_meta("created_at", now_iso())
        self.conn.commit()

    # -- context manager -------------------------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        try:
            self.conn.commit()
        finally:
            self.conn.close()

    # -- meta ------------------------------------------------------------------------------------
    def get_meta(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))

    # -- roots -----------------------------------------------------------------------------------
    def add_root(self, source) -> Tuple[int, str]:
        """Register a source folder (idempotent) and return ``(root_id, label)``."""
        absolute = os.path.abspath(str(source))
        if _is_within(absolute, str(self.base)):
            stored, is_relative = Path(os.path.relpath(absolute, str(self.base))).as_posix(), 1
        else:
            stored, is_relative = absolute, 0
        row = self.conn.execute("SELECT id, label FROM roots WHERE path=?", (stored,)).fetchone()
        if row:
            return row["id"], row["label"]
        label = base_label = Path(absolute).name or absolute
        counter = 2
        while self.conn.execute("SELECT 1 FROM roots WHERE label=?", (label,)).fetchone():
            label = f"{base_label}-{counter}"
            counter += 1
        cursor = self.conn.execute(
            "INSERT INTO roots(label, path, is_relative) VALUES (?, ?, ?)", (label, stored, is_relative)
        )
        self.conn.commit()
        return cursor.lastrowid, label

    def roots(self) -> List[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM roots ORDER BY id").fetchall()

    def root_path(self, root) -> Path:
        """Absolute folder of a root row (or root id) on the current machine."""
        if isinstance(root, int):
            root = self.conn.execute("SELECT * FROM roots WHERE id=?", (root,)).fetchone()
        if root["is_relative"]:
            return self.base.joinpath(*root["path"].split("/"))
        return Path(root["path"])

    def file_path(self, root_id: int, relpath: str) -> Path:
        return self.root_path(root_id).joinpath(*relpath.split("/"))

    # -- errors ----------------------------------------------------------------------------------
    def add_error(self, root_id: Optional[int], relpath: str, stage: str, error: str) -> None:
        """Record (or refresh) the error of one file/folder at one stage."""
        self.conn.execute("DELETE FROM scan_errors WHERE root_id IS ? AND relpath=? AND stage=?",
                          (root_id, relpath, stage))
        self.conn.execute(
            "INSERT INTO scan_errors(root_id, relpath, stage, error, at) VALUES (?, ?, ?, ?, ?)",
            (root_id, relpath, stage, error[:500], now_iso()),
        )


def default_workspace_for(source) -> Path:
    """``<drive root>/_versline_organize`` for a source folder (drive letter root on Windows, the
    mount point on Linux/macOS)."""
    path = Path(os.path.abspath(str(source)))
    if os.name == "nt":
        return Path(path.anchor) / WORKSPACE_DIRNAME
    current = path
    while not os.path.ismount(str(current)) and current.parent != current:
        current = current.parent
    return current / WORKSPACE_DIRNAME
