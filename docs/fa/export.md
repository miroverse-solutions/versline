# خروجی Word و PDF

[فهرست](index.md) · [English](../en/export.md) · **فارسی**

هر ماژول ورس‌لاین می‌تواند نتیجه را به‌صورت **Word (.docx)** و **PDF** هم بنویسد. تبدیل با [MdPersia](https://github.com/hamid-morsali-786/MdPersia) انجام می‌شود که متن فارسی/راست‌به‌چپ، جدول، کد و callout را درست پشتیبانی می‌کند. این بخش افزونه‌ی اختیاری است.

## نصب

```sh
pip install "versline[export]"     # نیاز به پایتون ۳.۱۱ به بالا
versline export --install-browser  # یک بار، فقط برای PDF: دانلود Chromium (حدود ۱۵۰ مگابایت)
```

- **Word** مرورگر نمی‌خواهد.
- **PDF** به Chromium نیاز دارد، یا Chrome/Edge نصب‌شده روی سیستم (به‌عنوان جایگزین).
- بدون این افزونه بقیه‌ی برنامه عادی کار می‌کند و `--export` راهنمای نصب را چاپ می‌کند.
- برای نمایش بهتر متن فارسی در Word، فونت Vazirmatn را نصب کنید (همراه برنامه است). در PDF فونت خودکار جاسازی می‌شود.

## در همه‌ی دستورها: `--export`

هر دستوری که Markdown می‌نویسد این گزینه‌ها را دارد:

| گزینه | معنی |
| :--- | :--- |
| `--export`، `-X FORMATS` | `docx`، `pdf`، `docx,pdf` یا `all`؛ فایل‌ها کنار نتیجه‌ی Markdown ساخته می‌شوند |
| `--export-frontmatter` / `--no-export-frontmatter` | با (پیش‌فرض) یا بدون جدول مشخصات |

```sh
versline summarize lecture.md --export docx,pdf
versline translate paper.md -l Persian -X pdf --no-export-frontmatter
versline qude notes.md --export pdf        # برگه‌ی سؤال قابل چاپ، با پاسخنامه
versline organize stats --export pdf
```

پشتیبانی‌شده: `transcribe`، `translate`، `summarize`، `research`، `qualcode`، `qude` (با یک برگه‌ی Markdown تازه)، `organize stats|dupes|plan|verify` و `telegram archive`. خروجی `slides` ارائه‌ی HTML تعاملی است و تبدیل نمی‌شود.

پیش‌فرض‌ها را می‌توان در `config.env` گذاشت: `VERSLINE_EXPORT_FORMATS`، `VERSLINE_EXPORT_FRONT_MATTER`، `VERSLINE_EXPORT_PAGE_FORMAT`، `VERSLINE_EXPORT_MARGIN`، `VERSLINE_EXPORT_FONT_SIZE`، `VERSLINE_EXPORT_LANDSCAPE`.

### با یا بدون فرانت‌متر

- **با** (پیش‌فرض): فرانت‌متر YAML فایل، به‌علاوه‌ی اطلاعاتی که ماژول می‌داند (مدل، حالت، منبع…)، به‌صورت یک جدول دوستونه زیر عنوان می‌آید. کلیدها برچسب فارسی دارند و کلیدهای فنی (`aliases`، `post_ids`…) پنهان می‌شوند. اگر سند فرانت‌متر خودش را دارد، مقدارهای آن مقدم است.
- **بدون**: هیچ مشخصاتی نیست و فقط محتوا می‌آید.

نحو Obsidian تبدیل می‌شود: `![[image.png]]` تصویر جاسازی می‌شود، دیگر پیوست‌ها (صوت و ویدیو) به `📎 نام` بدل می‌شوند، `[[note|alias]]` به متن alias، و calloutهای `> [!note]` به callout استاندارد.

## `versline export`

```sh
versline export فایل|پوشه|الگو [--to docx,pdf] [--front-matter/--no-front-matter]
                [-o DIR] [-r] [-f] [--page-format A4] [--margin 15mm] [--landscape] [--font-size 12]
versline export --install-browser
```

هر Markdown را تبدیل می‌کند. با `-o` و ورودی پوشه، ساختار پوشه حفظ می‌شود. خروجی‌های به‌روز، بدون `--force` رد می‌شوند.

## پایتون

```python
from pathlib import Path
from versline.services.docexport import ExportItem, ExportOptions, export_items

export_items(
    [ExportItem(out_base=Path("out/report"), text="# عنوان\n\nمتن", metadata={"model": "gpt"})],
    ExportOptions(formats=("docx", "pdf"), front_matter=True),
)
```

همه‌ی موارد برای هر قالب در یک دسته تبدیل می‌شوند، پس PDFها یک بار مرورگر را راه می‌اندازند.

## بسته‌ی تلگرام

[تلگرام ← بسته‌ی کامل](telegram.md#بستهی-کامل-و-مرتب)
