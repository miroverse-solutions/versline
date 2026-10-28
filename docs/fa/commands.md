# مرجع دستورها

[فهرست](index.md) · [English](../en/commands.md) · **فارسی**

گزینه‌های سراسری (`-v`، `--env-file`، `--extra-body`، `--version`) **قبل از** نام دستور می‌آیند؛ [تنظیمات](configuration.md#global-cli-options) را ببینید. مرجع دقیق و همیشه به‌روز: `versline <command> --help`.

**گزینه‌های مشترک LLM** (در بیشتر دستورها؛ مقدار تنظیمات را بازنویسی می‌کنند): `--model`، `--provider` (Google، OpenAI، OpenRouter، AvalAI، OpenAICompatible)، `--api-key`، `--api-endpoint`، `--proxy`، `--extra-body`.
**یادداشت برای پرامپت** (بیشتر دستورها): `--note TEXT` یک دستور اضافه به پرامپت می‌افزاید؛ `--note-file FILE` همین کار را از فایل `.md`/`.txt` انجام می‌دهد.

## دستورهای تنظیم

| دستور | توضیح |
| :--- | :--- |
| `versline init` | تنظیم تعاملی اولیه؛ `config.env` کاربر را می‌نویسد |
| `versline config [--show] [--path]` | نمایش تنظیمات (رازها پوشانده) یا فقط مسیر فایل |
| `versline update` | به‌روزرسانی به آخرین انتشار GitHub |

## `transcribe`

```sh
versline transcribe FILE_OR_URL [OPTIONS]
```

صوت/ویدیو با ffmpeg به تکه‌های هم‌پوشان (پیش‌فرض ۹۰۰ ثانیه با ۱۸۰ ثانیه هم‌پوشانی) تقسیم می‌شود، هر تکه با مدل و با بافت تکه‌های قبلی پیاده می‌شود و در پایان ادغام می‌گردد. لینک‌ها (`http(s)://`) ابتدا در `temp/downloads` دانلود می‌شوند. پیشرفت در `work_dir/<name>/progress.json` ذخیره می‌شود، پس اجرای ناتمام ادامه می‌یابد. در پایان گزارش هزینه چاپ می‌شود.

| گزینه | توضیح | پیش‌فرض |
| :--- | :--- | :--- |
| `-o, --output PATH` | فایل خروجی | `output/<name>.md` (با `--json` برابر `.json`) |
| `--chunk-size N`، `--overlap N` | طول تکه / هم‌پوشانی (ثانیه) | `900` / `180` |
| `--prompt-file FILE` | پرامپت سیستمی سفارشی | پرامپت فارسی داخلی |
| `-j, --json` | خروجی ساخت‌یافته‌ی JSON | خاموش |
| `-f, --force` | نادیده گرفتن کش | خاموش |
| `--skip-blocked` | عبور از تکه‌هایی که سرویس‌دهنده مسدود می‌کند (جای آن `[⚠️ chunk N/M skipped: ...]` می‌ماند) به‌جای توقف | خاموش |
| `--timestamped` | تولید بخش‌های زمان‌بندی‌شده. ابتدا STT بومی (`verbose_json`) و در صورت نبود، روش مبتنی بر تکه. نتیجه‌ی JSON و متن کامل در `.md` هم‌نام ذخیره می‌شود. | خاموش |
| `--timestamp-model` | مدل STT | `gpt-4o-mini-transcribe` |
| `--chunk-minutes N` | دقیقه در هر تکه برای مراحل مبتنی بر تکه | تنظیمات |
| `--native-timestamps-only` | به‌جای بازگشت به روش مبتنی بر تکه، خطا بده | خاموش |
| `--reuse-transcript` | رونویسی را رد کن، متن کش‌شده را استفاده کن و فقط زمان‌بندی را دوباره بساز (`--force` در این حالت فقط کش زمان‌بندی را پاک می‌کند) | خاموش |
| `--timestamp-provider/-api-key/-api-endpoint/-proxy/-language/-timeout` | اتصال STT (پیش‌فرض از تنظیمات LLM؛ زبان `fa`) | |

به‌علاوه‌ی گزینه‌های مشترک LLM و یادداشت.

## `translate`

```sh
versline translate FILE [-l LANGUAGE] [-o BASE_PATH] [-f]
```

`-l/--lang` پیش‌فرض `Persian`. `-o` مسیر پایه است: **هم** `.md` و **هم** `.txt` (بدون Markdown) نوشته می‌شود. `-f` کش را نادیده می‌گیرد. به‌علاوه‌ی گزینه‌های مشترک.

## `summarize`

```sh
versline summarize FILE [OPTIONS]
```

| گزینه | توضیح | پیش‌فرض |
| :--- | :--- | :--- |
| `-m, --mode` | `outline`، `detailed`، `slides` | `detailed` |
| `-c, --compression 1-100` | طول هدف به‌درصدِ متن اصلی | تصمیم مدل |
| `-l, --output-lang` | زبان خلاصه؛ `auto` یعنی همان زبان منبع | `auto` |
| `--preserve-terms / --no-preserve-terms` | هنگام تفاوت زبان، اصطلاح اصلی در پرانتز بیاید | روشن |
| `-d, --didactic` | بازساختار آموزشی دو مرحله‌ای (نقشه‌ی آموزش، سپس خروجی بازچیده‌شده؛ با کش پرامپت) | خاموش |
| `-o, --output` | فایل `.md` خروجی | `output/...` |

ورودی می‌تواند هر فایل پشتیبانی‌شده‌ی پردازشگر سند باشد (Markdown، متن، PDF، DOCX، PPTX و ...).

## `qude`

تولید سؤال و خروجی گرفتن.

```sh
versline qude INPUT_PATH [OPTIONS]    # فایل یا پوشه
```

| گزینه | توضیح | پیش‌فرض |
| :--- | :--- | :--- |
| `-o, --output` | پوشه‌ی خروجی | `output` |
| `-p, --provider` | `openai`، `avalai`، `gemini`، `openrouter`، `custom` | تنظیمات |
| `-m, --model`، `-k, --api-key`، `-b, --base-url`، `--proxy`، `--extra-body` | تنظیمات سرویس‌دهنده | |
| `-t, --type` | `mcq` یا `open` | `mcq` |
| `-l, --lang` | کد زبان | `en` |
| `-c, --count` | تعداد سؤال برای هر تکه/اسلاید | حداکثر ممکن |
| `--formats` | `csv`، `anki`، `html`، `all` (با ویرگول) | `all` |
| `--style FILE` | CSS سفارشی برای Anki/HTML | |
| `--prompt FILE` | پرامپت سفارشی | |
| `--slides-per-batch / --pages-per-batch / --words-per-batch` | اندازه‌ی دسته برای PPTX / PDF و DOCX / Markdown و متن | `5` / `5` / `2000` |
| `--answer-length` | برای `open`: تعداد کلمه (`200`)، `short`/`medium`/`long` یا `mixed` | |
| `-f, --force` / `--no-cache` / `-r, --regenerate` / `--debug` | نادیده گرفتن کش / خاموش کردن کش / بازسازی خروجی فقط از کش / اشکال‌زدایی | |
| `--note`، `--note-file` | دستور اضافه | |

## `qualcode`

کدگذاری کیفی فایل مصاحبه/متن.

```sh
versline qualcode INPUT_PATH [OPTIONS]
```

| گزینه | توضیح | پیش‌فرض |
| :--- | :--- | :--- |
| `-m, --method` (تکرارپذیر) | `thematic`، `grounded`، `content`، `framework`، `colaizzi` | `thematic` |
| `--format` (تکرارپذیر) | `json`، `markdown`، `csv`، `segments-csv`، `detailed-csv` | json و markdown |
| `--code TEXT` (تکرارپذیر)، `--codebook FILE` | کدهای اولیه / کدبوک (`.txt .md .csv .json`) | |
| `--central-concepts FILE` | فایل مفاهیم محوری | |
| `--code-mode` | `guided` یا `strict` | `guided` |
| `--analysis-language` | `auto`، `fa`، `en` | `auto` |
| `--words-per-batch` | سقف کلمه در هر دسته | `1200` |
| `--citation / --no-citation` | افزودن نقل‌قول‌های شاهد | خاموش |
| `--csv-fill-quotes-from-segments / --no-...` | پر کردن نقل‌قول‌های خالی CSV از متن بخش | روشن |
| `--excel / --no-excel` | کنار هر CSV فایل `.xlsx` هم بنویس | روشن |
| `--fail-on-parse-error` | اگر JSON یک دسته خوانده نشد، شکست بخور | خاموش |
| `-o`، `-f`، `-p/--provider`، `--model`، `--api-key`، `--api-endpoint`، `--proxy`، `--extra-body`، `--note`، `--note-file` | مثل بقیه | `-o output` |

## `research`

نگارش مرحله‌ای دانشگاهی؛ فعلاً بخش **یافته‌ها** (فصل ۴) با روش `thematic-colaizzi`.

1. `--stage outline` طرح کلی فصل را می‌سازد.
2. شما طرح را بازبینی/ویرایش می‌کنید.
3. `--stage full` متن نهایی را می‌نویسد. بدون هر دو گزینه‌ی `--approved-outline-file` و `--approve-outline` **مسدود** است.

| گزینه | توضیح | پیش‌فرض |
| :--- | :--- | :--- |
| `-i, --input-json FILE` | اطلاعات و مواد پژوهش (الگو در ادامه) | |
| `-s, --stage` | `outline` یا `full` | `outline` |
| `--section`، `-m, --method` | بخش / روش | `findings` / `thematic-colaizzi` |
| `-l, --output-lang` | `auto` یعنی زبان منبع | `auto` |
| `--approved-outline-file`، `--approve-outline` | برای `full` الزامی | |
| `--demographics-file`، `--themes-table-file`، `--central-concepts-file` | فایل‌های مواد (csv/xlsx/md/txt/docx/pdf) | |
| `--coded-segments-file` (تکرارپذیر)، `--coded-segments-dir` | خروجی‌های تحلیل (کدها، MAXQDA، ماتریس مضامین) | |
| `--interview-file` (تکرارپذیر)، `--interviews-dir` | فقط متن خام مصاحبه‌ها | |
| `--writing-guide-file` | ساختار و سبک الزامی فصل | |
| `--sample-output-file` | نمونه‌ی سبک | |
| `--revision-file` | شرح اصلاحات برای اجرای مجدد | |
| `--revision-history-file` | تاریخچه‌ی تجمعی اصلاحات (JSON) | فایل خودکار `<outline_stem>.revision-history.json` |
| `-o, --output` | فایل `.md` خروجی | `output/<stem>_<section>_<stage>.md` |

به‌علاوه‌ی گزینه‌های مشترک LLM و یادداشت. نکته‌ها: فقط متن توصیفی فصل ۴ نوشته می‌شود (بدون بحث و نتیجه‌گیری)؛ داده‌ی ناموجود به‌صورت `[NEEDS DATA: ...]` می‌آید؛ نقل‌قول و فراوانی باید از مواد داده‌شده باشد. همه‌ی شرح اصلاحات در فایل تاریخچه جمع می‌شود و در اجراهای بعدی دوباره اعمال می‌شود. ورودی `.docx` از طریق MarkItDown خوانده می‌شود.

```json
{
  "study": {
    "title": "عنوان پایان‌نامه", "domain": "روان‌شناسی",
    "section_goal": "Chapter 4 findings", "method": "thematic-colaizzi",
    "research_questions": ["سؤال ۱", "سؤال ۲"]
  },
  "materials": {
    "demographics_table": "اختیاری",
    "themes_table": "اختیاری", "central_concepts": "اختیاری", "coded_segments": "اختیاری",
    "interviews": [{ "name": "interview_01.md", "content": "متن اختیاری" }]
  }
}
```

```sh
versline research -i study.json --stage outline --demographics-file demo.xlsx \
  --coded-segments-dir ./coded --writing-guide-file guide.md -o output/ch4_outline.md
versline research -i study.json --stage full --approved-outline-file output/ch4_outline_approved.md \
  --approve-outline --revision-file revisions.md -o output/ch4_full.md
```

## `slides`

ساخت اسلاید HTML/CSS/TypeScript از فایل Markdown.

| گزینه | توضیح | پیش‌فرض |
| :--- | :--- | :--- |
| `-o, --output` | پوشه‌ی خروجی | `output` |
| `--prompt-file`، `--font-file`، `--font-family` | پرامپت سفارشی / فونت محلی (`.ttf .otf .woff .woff2`) / نام خانواده در CSS | `Vazirmatn` (همراه برنامه) |
| `--build`، `--single-file`، `--install-deps / --no-install-deps` | ساخت با Vite (نیازمند Node/npm)؛ خروجی تک‌فایل؛ نصب وابستگی‌های npm پیش از ساخت | خاموش، خاموش، روشن |
| `--npm-registry URL` | رجیستری برای `--build` | `VERSLINE_SLIDES_NPM_REGISTRY` |
| `--include-all-content` / `--verbatim-text` | هیچ محتوایی حذف نشود / فقط متن عین منبع | خاموش |
| `--no-scroll / --allow-scroll` | جا دادن همه‌ی محتوا بدون اسکرول | no-scroll |
| `--uniform-size / --no-uniform-size`، `--slide-size` | اندازه‌ی یکسان؛ `small` ‏720×480، `medium` ‏960×640، `large` ‏1280×800 | روشن، `medium` |
| `--chunk-size N` | تولید تدریجی از تکه‌های حدود N نویسه (۰ = کل فایل) | `0` |
| `--impress` | اسلاید سه‌بعدی Impress.js (HTML مستقل) | خاموش |
| `--revealjs` | اسلاید Reveal.js | خاموش |

به‌علاوه‌ی گزینه‌های مشترک LLM و یادداشت.

## `telegram`

`telegram login`، `telegram logout`، `telegram archive CHANNEL`. توضیح کامل در [بایگانی کانال تلگرام](telegram.md).

## موجود نیست

`download` در سورس هست (`commands/download.py`) ولی در خط فرمان **ثبت نشده است**. برای دانلود یک لینک، آن را مستقیم به `versline transcribe` بدهید.
