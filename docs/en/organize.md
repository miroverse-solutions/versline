# Organizing a file archive (`organize`)

[Index](index.md) · [Design (Persian)](../fa/organize-design.md) · **English** · [فارسی](../fa/organize.md)

`versline organize` is for large, messy drives: tens of thousands of books, notes, audio, video and scanned pages
piled up over years from several sources. It first builds a **complete catalogue**, then finds **duplicates**, and
(in development) builds a **clean structure next to the existing data**.

> **Your files are never touched.** No command deletes, moves or renames anything in the source folders. Every
> output goes to a separate `_versline_organize` folder.
>
> **No API key needed.** The current steps use no AI.

## Steps

| Step | Command | Status |
|---|---|---|
| 1. Catalogue | `versline organize scan` | ✅ |
| 2. Statistics | `versline organize stats` (runs after scan) | ✅ |
| 3. Duplicates | `versline organize dupes` | ✅ |
| 4. Excel export of every file | `versline organize export` | ✅ |
| Status | `versline organize status` | ✅ |
| 5. Classify, plan, copy, verify | `classify`, `plan`, `apply`, `verify` | ⏳ in development (see the design doc) |

## Quick start

```powershell
# Windows, drive E:
E:
versline organize scan "E:\Library" "E:\Old drive dump"
versline organize dupes
versline organize export
```

```sh
# Linux
cd "/run/media/$USER/MyDrive"
versline organize scan Library "Old drive dump"
versline organize dupes
versline organize export
```

The workspace is created at the **root of the drive** of the first source (`E:\_versline_organize`); use `-w PATH`
to put it elsewhere. `stats`, `dupes`, `export` and `status` find it automatically when run from the drive root.

**Move the drive between Windows and Linux freely:** paths are stored relative to the drive root, so a scan done on
Linux can be continued on Windows under any drive letter.

## Commands

| Command | What it does |
|---|---|
| `scan SOURCE... [-w WS] [--no-stats]` | Records every file (name, size, mtime, kind) in `catalog.sqlite`. Incremental; files gone from a source are flagged missing, not deleted. Skips `$RECYCLE.BIN`, `System Volume Information`, Linux trash and the workspace. Detects scanned-book folders (mostly images) and software folders (mostly exe/dll). |
| `stats [-w WS]` | Writes `reports/stats.md` (per source, per kind, top extensions, special folders, read errors). |
| `dupes [-w WS] [--min-size 1MB] [--folder-ratio 0.9]` | Finds byte-identical files: same size → SHA-256 of first+last 64 KB → full SHA-256. Every hash is saved immediately, so it can be interrupted and resumed. Writes `reports/duplicates.md`, `duplicates.csv` and `redundant_folders.csv` (folders whose bytes ≥ 90% also exist elsewhere). |
| `export [-w WS]` | Writes `reports/files.csv` (every file with kind, size, date, SHA-256 when computed, copy count). UTF-8 with BOM so Excel shows Persian correctly. |
| `status [-w WS]` | Summary of sources, counts, hashes and last scan time. |

## Workspace

```
_versline_organize/
├── catalog.sqlite      ← the catalogue (readable with any SQLite tool)
├── reports/            ← Markdown and CSV reports
├── logs/organize.log
```

Do not delete it: it holds all progress. Losing it only means re-scanning and re-hashing; your files are unaffected.

## Notes

- Speed: scanning 50k files takes under a minute; `dupes` reads only same-size candidates (≈50–100 MB/s on a USB
  drive).
- A few files may fail with "Operation not supported" on Linux (cloud-only OneDrive placeholders or special NTFS
  files). They are listed in `reports/scan_errors.csv`; check them on Windows.
- Hard links for the planned copy step need NTFS.
- Everything is in open formats (SQLite, CSV, Markdown), so the work can continue without Versline; see section 11
  of the design document.
