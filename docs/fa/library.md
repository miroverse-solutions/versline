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
