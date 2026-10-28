# معماری و توسعه

[فهرست](index.md) · [English](../en/architecture.md) · **فارسی**

## ساختار (`src/versline/`)

| مسیر | نقش |
| :--- | :--- |
| `cli.py` | برنامه‌ی Typer، گزینه‌های سراسری، اعلان به‌روزرسانی. ماژول‌های سنگین lazy بارگذاری می‌شوند تا `init/config/update/--version` سریع باشند |
| `commands/` | پوشش‌های نازک خط فرمان (`transcribe`، `translate`، `summarize`، `qude`، `qualcode`، `research`، `slides`، `telegram`، `setup`) |
| `config.py`، `userconfig.py` | گروه‌های تنظیمات pydantic-settings (llm، transcription، ffmpeg، resource، slides، telegram)، بارگذاری env، پوشه‌ی تنظیمات کاربر |
| `services/` | منطق اصلی: `transcription`، `translation`، `summarizer`، `question_generator`، `qualitative_coding`، `research_writing`، `slides`، `document_processor`، `export`، `media`، `network`، `ai` (کلاینت سرویس‌دهنده‌ها، تلاش مجدد)، `pricing` (پایش توکن/هزینه) |
| `services/channel_archive/` | بایگانی تلگرام: `sources/` (`telegram` با Telethon، `telegram_web` با httpx و BeautifulSoup)، `steps.py` (رسانه، پیاده‌سازی، خلاصه، تقریر)، `pipeline.py`، `obsidian.py`، `state.py` (فایل وضعیت)، `llm.py` (تولیدکننده‌ی متن تک‌پرامپتی)، `models.py` |
| `core/` | ثابت‌ها، نوع‌ها، بارگذاری پرامپت، محدودیت منابع |
| `mcp/server.py` | ابزارهای MCP |
| `resources/prompts`، `resources/assets` | پرامپت‌ها، فونت وزیرمتن و فایل‌های اسلاید |

سرویس‌دهنده‌ها: Google (google-genai با کش زمینه)، OpenAI، OpenRouter، AvalAI (استعلام دقیق هزینه) و سازگار با OpenAI. فراخوانی‌های API خودکار دوباره تلاش می‌شوند؛ مصرف توکن و هزینه ثبت و در پایان اجرا چاپ می‌شود.

## خط لوله‌ی تلگرام

برای هر پست انتخاب‌شده `ChannelArchiver` مراحل را به ترتیب اجرا می‌کند: **رسانه** (فقط آنچه لازم است دانلود می‌شود؛ فایل‌های موقت جز با `--keep-media` حذف می‌شوند) ← **پیاده‌سازی** (ویدیو با ffmpeg به mp3 تبدیل می‌شود، پیاده‌سازی تکه‌ای، کش در `work_dir/<stem>/progress.json`) ← **خلاصه** ← **تقریر**. یادداشت به‌صورت اتمی نوشته می‌شود و فایل وضعیت به‌روز می‌گردد؛ خطاها برای هر پست جدا هستند.

## پایداری

نوشتن فایل‌ها اتمی است (فایل موقت، سپس جایگزینی)؛ پست‌های ناموفق در اجرای بعد دوباره تلاش می‌شوند؛ پیاده‌سازی تکه‌به‌تکه قابل ادامه است. دستورها در خطا با کد ۱ خارج می‌شوند.

## آزمون‌ها

```sh
make test      # python -m pytest tests -q
```

۲۱ فایل آزمون، شامل تنظیمات، محدودیت منابع، پیاده‌سازی (انتخاب سرویس‌دهنده، بازگشت STT، هم‌ترازی کلمات)، خلاصه‌ساز، اسلاید، qude، qualcode، research، هزینه و بایگانی تلگرام (`test_channel_obsidian.py`، `test_channel_pipeline.py`، `test_channel_web.py`). CI روی Ubuntu، Windows و macOS با Python 3.12 اجرا می‌شود.

## انتشار

[نصب](installation.md#releasing-maintainers) را ببینید. بسته‌ی ویندوز با `packaging/build.py` ساخته می‌شود (PyInstaller به‌صورت `--onedir`، ffmpeg از پیش دریافت‌شده، آزمون دود با `versline.exe --version`).
