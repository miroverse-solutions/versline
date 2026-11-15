# کتابخانه‌ی پایتون و سرور MCP

[فهرست](index.md) · [English](../en/library.md) · **فارسی**

## کتابخانه

```python
from versline import (AudioTranscriber, TextTranslator, QualitativeCoder,
                      MarkdownSlideDeckGenerator, download_file, settings, reload_settings)

reload_settings("/path/to/.env")          # اختیاری: بارگذاری یک فایل env مشخص
settings.llm.provider = "AvalAI"
settings.llm.api_key = "YOUR_API_KEY"
settings.llm.model = "gpt-4o-mini"
settings.llm.proxy = "socks5://127.0.0.1:10808"   # اختیاری
```

خروجی‌های بسته به‌صورت lazy بارگذاری می‌شوند و `import versline` سریع می‌ماند.

**پیاده‌سازی متن**

```python
transcriber = AudioTranscriber()
text = transcriber.process_file("interview.mp3")

result = transcriber.process_file("lecture.mp3", timestamped=True,
                                  timestamp_model="gpt-4o-mini-transcribe", chunk_minutes=3)
print(result["text"])
for seg in result["segments"]:
    print(int(seg["start"] // 60), seg["text"][:100])
```

**ترجمه**

```python
TextTranslator().process_file("document.txt", target_language="German")
```

**خلاصه‌سازی**

```python
from versline.services.summarizer import TextSummarizer
TextSummarizer(mode="detailed").process_file("lecture.pdf")
TextSummarizer(mode="detailed", output_lang="Persian", preserve_terms=True).process_file("paper.md")
TextSummarizer(mode="detailed", didactic=True).process_file("textbook.md")
TextSummarizer(mode="slides", output_lang="English").process_file("report.docx")
```

**کدگذاری کیفی**

```python
coder = QualitativeCoder(output_dir="output", methods=["colaizzi"],
                         output_formats=["json", "csv", "segments-csv"],
                         code_mode="guided", analysis_language="fa", include_citation=True)
outputs = coder.process_file("interview.md")
print(outputs, coder.last_parse_failures)
```

**اسلاید**

```python
MarkdownSlideDeckGenerator().generate_from_markdown(
    input_path="talk.md", output_dir="output", build=True, single_file=True, install_deps=True)
```

**محدودیت منابع** (هرگز خودکار اعمال نمی‌شود)

```python
from versline.core.resources import apply_resource_limits
apply_resource_limits(max_ram_mb=4096, max_cpu_cores=4, max_gpu_vram_fraction=0.7)
```

## سرور MCP

فایل `src/versline/mcp/server.py` یک سرور FastMCP است (`python -m versline.mcp.server`) که ابزارهایی را فراهم می‌کند که خط فرمان را صدا می‌زنند: `transcribe`، `translate`، `summarize`، `generate_questions`، `generate_slides`، `transcribe_text`، `translate_text`، `summarize_text`. اسکریپت `versline-mcp.sh` در مخزن آن را با `venv/bin/python3` یک checkout سورس اجرا می‌کند. به‌عنوان دستور جداگانه نصب نمی‌شود.

## پروتکل bridge

`versline bridge` یک رابط ماشین‌خوان برای برنامه‌های دیگر است. [افزونه‌ی Obsidian یعنی Versobs](obsidian.md) از آن استفاده می‌کند و ویرایشگرها و اسکریپت‌ها هم می‌توانند از آن استفاده کنند. همان کدِ دستورهای خط فرمان را اجرا می‌کند (پردازش دسته‌ای، ادامه‌ی کار نیمه‌تمام، رد شدن از کارهای انجام‌شده، خروجی Word/PDF)، اما ورودی و خروجی‌اش JSON است.

```sh
versline bridge info --pretty                  # نسخه‌ها و همه‌ی ابزارها با JSON Schema پارامترها
echo '{"params": {"inputs": ["lecture.pdf"], "output": "/notes/lecture_summary.md", "mode": "outline"}}' \
  | versline bridge run summarize.file
```

**درخواست:** یک خط JSON روی stdin (یا با `--params` / `--params-file`) به شکل `{"params": {...}, "llm": {"provider", "model", "api_key", "api_endpoint", "proxy", "extra_body"}, "workdir": "..."}`. فقط `params` لازم است و فرستادن خودِ شیء پارامترها هم کار می‌کند. مقادیر `llm` تنظیمات ذخیره‌شده را فقط برای همین کار تغییر می‌دهند؛ بهتر است کلید را با متغیر محیطی `VERSLINE_LLM_API_KEY` بفرستید. کش‌ها و فایل‌های موقت در `--workdir` ذخیره می‌شوند (پیش‌فرض: `~/.cache/versline/bridge` یا `%LOCALAPPDATA%\versline\bridge`). مسیرها را کامل (مطلق) بدهید.

**رویدادها:** در هر خطِ stdout یک شیء JSON. هیچ چیز دیگری آنجا نوشته نمی‌شود و هر چاپ پراکنده‌ای به رویداد `log` تبدیل می‌شود.

| `type` | فیلدها |
| :--- | :--- |
| `hello` | `versline`، `protocol` (فعلاً 1)، `tool` |
| `progress` | `current`، `total` (null یعنی نامعلوم)، `label` |
| `log` | `level` (debug، info، success، warning، error)، `message` |
| `prompt` | `id`، `message`، `secret`، `kind` (phone، code، password، api_id، api_hash، confirm یا null)، `default`، `choices` |
| `artifact` | `path`، `kind` (note، folder، media، pdf، docx و…)، `exists`: فایلی که کار ساخته یا تغییر داده |
| `cost` | `input_tokens`، `output_tokens`، `cached_tokens`، `usd`، `irt`، `error` |
| `result` | `data` (بسته به ابزار، معمولاً `outputs`)، `artifacts`: آخرین رویدادِ اجرای موفق (کد خروج 0) |
| `error` | `code` (unknown_tool، invalid_params، bad_input، failed، cancelled، exception، internal)، `message`: آخرین رویدادِ اجرای ناموفق (کد خروج 1؛ 2 برای درخواست نامعتبر؛ 130 برای لغو) |

**در حین اجرا** با `{"type": "answer", "id": "p1", "value": "..."}` به یک پرسش پاسخ دهید (مقدار `null` یعنی رد کردن) و با `{"type": "cancel"}` کار را متوقف کنید. اگر stdin در حالی بسته شود که پرسشی منتظر پاسخ است، کار لغو می‌شود. بستن (kill) پروسس هم بی‌خطر است، چون بخش‌های تمام‌شده در کش مانده‌اند.

**Schema‌ی ابزارها** راهنمای رابط کاربری دارد تا هر برنامه‌ای بتواند برای هر ابزاری فرم بسازد: `x-label`/`x-help` (`{"en", "fa"}`)، `x-widget` (file، files، folder، textarea، secret، output-file، output-folder، date، tags)، `x-accept` (پسوندها)، `x-advanced`، `x-output` (الگوی پیش‌فرض خروجی مثل `{dir}/{stem}_summary_{mode}.md`) و `x-choices` (برچسب گزینه‌ها). ابزارهایی که `hidden` هستند ابزارهای داخلی‌اند (تنظیمات، ورود به تلگرام، به‌روزرسانی) و در فهرست عمومی ابزارها نمی‌آیند.

**افزودن ابزار:** در `src/versline/bridge/tools/` یک مدل `Params` با فیلدهای `F(...)` تعریف کنید، یک تابع را با `@tool(...)` علامت بزنید و دستور خط فرمان را با `run_command(ctx, "versline.commands.x", "func", outputs=[...], **options)` صدا بزنید. سپس ماژول را در `tools/__init__.py` import کنید. تست `tests/test_bridge.py` بررسی می‌کند که هر گزینه‌ای که فرستاده می‌شود در خود دستور وجود داشته باشد.
