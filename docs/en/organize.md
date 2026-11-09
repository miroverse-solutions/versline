# Organizing a file archive (`organize`)

[Index](index.md) · [Design (Persian)](../fa/organize-design.md) · **English** · [فارسی](../fa/organize.md)

`versline organize` is for large, messy drives: tens of thousands of books, notes, audio, video and scanned pages
piled up over years from several sources. It first builds a **complete catalogue**, then finds **duplicates**, and
builds a **plan** from rules you control, and after your approval builds a **clean structure next to the existing data**.

> **Nothing is deleted or overwritten.** Every command except `apply` is read-only. `apply` **copies** files and
> **moves** only audio/video (configurable) on the same drive; every move is journaled and `revert-moves` undoes it.
>
> **No API key needed.** No step uses AI.

## Steps

| Step | Command | Status |
|---|---|---|
| 1. Catalogue | `versline organize scan` | ✅ |
| 2. Statistics | `versline organize stats` (runs after scan) | ✅ |
| 3. Duplicates | `versline organize dupes` | ✅ |
| 4. Excel export of every file | `versline organize export` | ✅ |
| Status | `versline organize status` | ✅ |
| 5. Destination structure and rules | `taxonomy.txt`, `rules.txt` in the workspace | ✅ |
| 6. Plan (preview, changes nothing) | `versline organize plan` | ✅ |
| 7. Execute: copy + move media | `versline organize apply [--dry-run] [--only move\|copy] [--yes]` | ✅ |
| 8. Verify and coverage report | `versline organize verify [--deep]` | ✅ |
| Undo the moves | `versline organize revert-moves` | ✅ |
| AI rule suggestions | `classify --llm` | ⏳ |

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

## Rules, plan, apply

`rules.txt` maps source prefixes to destination folders (`source label/folder => destination/folder`); the longest
matching prefix wins and sub-folders are kept. Directives: `@dest_root`, `@default` (unmatched files),
`@root_priority` (which duplicate keeps the plain name), `@media from => to` (re-root audio/video destinations),
`@media_kinds`, `@media_folder_ratio` (other files in a media-heavy folder follow the media). Per-file decisions go in an optional `assignments.csv` (columns `root,path,dest,by,note`; `dest` is the
destination folder), which wins over every rule. `taxonomy.txt` lists
the agreed destination folders; `plan` warns about rules pointing elsewhere.

`plan` writes `plan/plan_summary.md` (read this first) and `plan/plan.csv` (one row per file; set `approved` to
`no` to exclude a row; save from Excel as "CSV UTF-8"). Actions: `move` (audio/video, same-drive rename),
`copy`, `skip_duplicate` (identical content copied elsewhere), `skip_junk`.

`apply --skip-unclassified` leaves files without a rule (bound for the `@default` archive) for a later run.
`apply` runs moves first, then copies (written to `.part`, SHA-256 checked, then renamed). It checks free space,
asks for confirmation (`--yes` to skip), never overwrites an existing file, and resumes where it stopped.
`verify` writes `reports/verify.md` and `coverage.csv`; `revert-moves` puts every moved file back (the journal is
also exported to `logs/moves.csv`, rebuilt from the database after every run, paths relative to the drive root). Full details: section 6.7–6.8 of the design document.

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
- `move` only works within one drive, so `@dest_root` must be on the same drive as the sources.
- Everything is in open formats (SQLite, CSV, Markdown), so the work can continue without Versline; see section 11
  of the design document.
