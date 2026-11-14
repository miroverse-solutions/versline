# Word and PDF export

[Index](index.md) · **English** · [فارسی](../fa/export.md)

Every Versline module can also write its result as **Word (.docx)** and **PDF**. The conversion uses [MdPersia](https://github.com/hamid-morsali-786/MdPersia), which handles Persian/RTL text, tables, code and callouts. It is an optional extra.

## Install

```sh
pip install "versline[export]"     # needs Python 3.11+
versline export --install-browser  # one time, PDF only: downloads Chromium (~150 MB)
```

- **Word** needs no browser.
- **PDF** needs Chromium, or Chrome/Edge already installed on the machine (used as a fallback).
- Without the extra, everything else keeps working; `--export` prints an install hint.
- Word shows Persian text best with the Vazirmatn font installed (it is bundled in `resources/assets`). PDFs embed it automatically.

## Anywhere: `--export`

Every module that writes Markdown accepts:

| Option | Meaning |
| :--- | :--- |
| `--export`, `-X FORMATS` | `docx`, `pdf`, `docx,pdf` or `all`. Files are written next to the Markdown result |
| `--export-frontmatter` / `--no-export-frontmatter` | With (default) or without the metadata table |

```sh
versline summarize lecture.md --export docx,pdf
versline translate paper.md -l Persian -X pdf --no-export-frontmatter
versline qude notes.md --export pdf        # writes a printable question sheet with an answer key
versline organize stats --export pdf
```

Supported: `transcribe`, `translate`, `summarize`, `research`, `qualcode`, `qude` (via a new question-sheet Markdown), `organize stats|dupes|plan|verify`, and `telegram archive`. `slides` produces an interactive HTML deck, so it is not exported.

Defaults can be set in `config.env`: `VERSLINE_EXPORT_FORMATS`, `VERSLINE_EXPORT_FRONT_MATTER`, `VERSLINE_EXPORT_PAGE_FORMAT`, `VERSLINE_EXPORT_MARGIN`, `VERSLINE_EXPORT_FONT_SIZE`, `VERSLINE_EXPORT_LANDSCAPE`.

### With or without front matter

- **With** (default): the file's YAML front matter, plus information the module knows (model, mode, source…), becomes a small two-column table under the title. Keys are shown with Persian labels; noisy keys (`aliases`, `post_ids`…) are hidden. If the document has its own front matter, its values win.
- **Without**: no metadata at all; just the content.

Obsidian syntax is converted: `![[image.png]]` is embedded, other embeds (audio, video) become `📎 name`, `[[note|alias]]` becomes the alias, and `> [!note]` callouts become standard callouts.

## `versline export`

```sh
versline export FILES|FOLDERS|GLOBS [--to docx,pdf] [--front-matter/--no-front-matter]
                [-o DIR] [-r] [-f] [--page-format A4] [--margin 15mm] [--landscape] [--font-size 12]
versline export --install-browser
```

Converts any Markdown. With `-o` and a folder input the folder layout is mirrored. Up-to-date outputs are skipped unless `--force`.

## Python

```python
from pathlib import Path
from versline.services.docexport import ExportItem, ExportOptions, export_items

export_items(
    [ExportItem(out_base=Path("out/report"), text="# Title\n\nBody", metadata={"model": "gpt"})],
    ExportOptions(formats=("docx", "pdf"), front_matter=True),
)
```

All items go through one batch per format, so PDFs share one browser launch.

## Telegram pack

See [Telegram → Pack](telegram.md#pack-a-complete-tidy-package).
