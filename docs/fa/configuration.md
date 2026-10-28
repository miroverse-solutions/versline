# تنظیمات

[فهرست](index.md) · [English](../en/configuration.md) · **فارسی**

<a id="where-settings-live"></a>
## تنظیمات کجا ذخیره می‌شود

ساده‌ترین راه دستور `versline init` است. سرویس‌دهنده (Google، OpenAI، OpenRouter، AvalAI، OpenAICompatible)، کلید API (پنهان)، مدل، آدرس سرویس (فقط OpenAICompatible) و پروکسی (اختیاری) را می‌پرسد و به‌صورت متغیرهای `VERSLINE_LLM_*` در فایل `config.env` کاربر (با دسترسی ۶۰۰) ذخیره می‌کند.

| مورد | مسیر |
| :--- | :--- |
| پوشه‌ی تنظیمات کاربر | `$VERSLINE_CONFIG_DIR`، وگرنه `%APPDATA%\versline` (ویندوز)، وگرنه `$XDG_CONFIG_HOME/versline` یا `~/.config/versline` |
| فایل تنظیمات | `<پوشه‌ی تنظیمات>/config.env` |
| حافظه‌ی بررسی به‌روزرسانی | `<پوشه‌ی تنظیمات>/last_update_check.json` |
| نشست تلگرام | `<پوشه‌ی تنظیمات>/telegram.session` |

مدل‌های پیش‌فرض `init`: Google ‏`gemini-2.0-flash`، OpenAI ‏`gpt-4o-mini`، OpenRouter ‏`~google/gemini-flash-latest`، AvalAI ‏`gemini-2.0-flash`.

```sh
versline config          # نمایش تنظیمات ذخیره‌شده (کلید/توکن/راز پوشانده می‌شود)
versline config --path   # فقط مسیر config.env
```

## اولویت منابع (از بالا به پایین)

1. گزینه‌های خط فرمان (`--api-key`، `--model`، `--proxy` و ...)
2. `versline --env-file /path/.env <command>` (گزینه‌ی سراسری، باید قبل از دستور بیاید)
3. متغیرهای محیطی واقعی (`VERSLINE_*`)
4. فایلی که `VERSLINE_ENV_FILE` به آن اشاره می‌کند
5. فایل `.env` در پوشه‌ی جاری
6. فایل `config.env` کاربر

در حالت کتابخانه، برای تحمیل قطعی یک فایل مشخص از `reload_settings("/path/.env")` استفاده کنید.

<a id="global-cli-options"></a>
## گزینه‌های سراسری

قبل از نام دستور می‌آیند: `versline [OPTIONS] COMMAND ...`

| گزینه | توضیح |
| :--- | :--- |
| `--version` | نمایش نسخه |
| `-v`، `--verbose` | لاگ جزئی (پیش‌فرض سطح INFO) |
| `--env-file PATH` | بارگذاری این فایل env پیش از اجرا (باید وجود داشته باشد) |
| `--extra-body JSON` | شیء JSON که به بدنه‌ی همه‌ی درخواست‌های سازگار با OpenAI اضافه می‌شود، مثل `'{"reasoning": {"max_tokens": 1500}}'`. روی Gemini بومی اعمال نمی‌شود. |
| `--install-completion`، `--show-completion` | تکمیل خودکار شل |

## متغیرهای محیطی

### مدل زبانی (LLM)

| متغیر | پیش‌فرض | توضیح |
| :--- | :--- | :--- |
| `VERSLINE_LLM_PROVIDER` | `Google` | `Google`، `OpenAI`، `OpenRouter`، `AvalAI`، `OpenAICompatible` |
| `VERSLINE_LLM_API_KEY` | | کلید API |
| `VERSLINE_LLM_MODEL` | `gemini-2.0-flash` | شناسه‌ی مدل |
| `VERSLINE_LLM_API_ENDPOINT` | | آدرس پایه‌ی سفارشی (برای `OpenAICompatible` الزامی؛ پیش‌فرض AvalAI ‏`https://api.avalai.ir/v1` و OpenRouter ‏`https://openrouter.ai/api/v1`) |
| `VERSLINE_LLM_PROXY` | | `socks5://host:port` یا `http://host:port` |
| `VERSLINE_LLM_AVALAI_PROVIDER` | | راهنمای مسیریابی AvalAI (`google`، `openai`، `anthropic`) |
| `VERSLINE_LLM_EXTRA_BODY` | | JSON اضافه برای بدنه‌ی درخواست‌های سازگار با OpenAI |

### زمان‌بندی در پیاده‌سازی متن

برای `transcribe --timestamped`. مقدارهای خالیِ اتصال به تنظیم متناظر `VERSLINE_LLM_*` برمی‌گردند.

| متغیر | پیش‌فرض | توضیح |
| :--- | :--- | :--- |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_MODEL` | `gpt-4o-mini-transcribe` | مدل STT |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_CHUNK_MINUTES` | `3` | طول هر تکه در روش جایگزین مبتنی بر تکه |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_PROVIDER` | | `OpenAI`، `AvalAI`، `OpenRouter`، `OpenAICompatible` |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_API_KEY` | | کلید API سرویس STT |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_API_ENDPOINT` | | آدرس پایه بدون `/audio/transcriptions` |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_PROXY` | | پروکسی STT |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_LANGUAGE` | `fa` | کد زبان (خالی = تشخیص خودکار) |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_TIMEOUT_SECONDS` | `120` | مهلت HTTP (نام قدیمی: `VERSLINE_TRANSCRIPTION_STT_TIMEOUT_SECONDS`) |

<a id="media"></a>
### رسانه

| متغیر | توضیح |
| :--- | :--- |
| `VERSLINE_FFMPEG_FFMPEG_PATH`، `VERSLINE_FFMPEG_FFPROBE_PATH` | مسیر صریح فایل‌ها. در غیر این صورت ffmpeg از `PATH` و سپس از نسخه‌ی همراه/`static-ffmpeg` برداشته می‌شود. |

### عمومی

| متغیر | پیش‌فرض | توضیح |
| :--- | :--- | :--- |
| `VERSLINE_OUTPUT_DIRECTORY` | `output` | پوشه‌ی خروجی پیش‌فرض |
| `VERSLINE_TEMP_DIRECTORY` | `temp` | دانلودها و فایل‌های موقت |
| `VERSLINE_SLIDES_NPM_REGISTRY` | | رجیستری npm برای `slides --build` |
| `VERSLINE_ENV_FILE` | | فایل env جایگزین |
| `VERSLINE_CONFIG_DIR` | | تغییر پوشه‌ی تنظیمات کاربر |

### تلگرام

| متغیر | توضیح |
| :--- | :--- |
| `VERSLINE_TELEGRAM_API_ID`، `VERSLINE_TELEGRAM_API_HASH` | از <https://my.telegram.org> (فقط حالت ورود با حساب) |
| `VERSLINE_TELEGRAM_PROXY` | پروکسی تلگرام (در غیر این صورت `VERSLINE_LLM_PROXY`) |
| `VERSLINE_TELEGRAM_SESSION_PATH` | مسیر سفارشی فایل نشست |

<a id="resource-limits-library-only"></a>
### محدودیت منابع (فقط کتابخانه)

`VERSLINE_RESOURCE_MAX_RAM_MB`، `VERSLINE_RESOURCE_MAX_CPU_CORES`، `VERSLINE_RESOURCE_MAX_GPU_VRAM_FRACTION` (پیش‌فرض `0` = نامحدود)، `VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT` (بین ۵۰ تا ۱۰۰، پیش‌فرض ۸۵) و `VERSLINE_RESOURCE_RUN_WATCHDOG_WITH_CGROUP`.

> خط فرمان این محدودیت‌ها را **به‌طور خودکار اعمال نمی‌کند**. فقط وقتی اثر دارند که کد شما `versline.core.resources.apply_resource_limits(...)` را صدا بزند: RAM با cgroup v2 ‏`memory.max` (لینوکس، با نگهبان RSS به‌عنوان جایگزین)، CPU با `os.sched_setaffinity` (لینوکس/POSIX) و GPU با `torch.cuda.set_per_process_memory_fraction`.

## نمونه‌ی `.env`

الگوی کامل و توضیح‌دار در فایل [`.env.example`](../../.env.example) مخزن است.

```dotenv
VERSLINE_LLM_PROVIDER=OpenRouter
VERSLINE_LLM_API_KEY=sk-or-...
VERSLINE_LLM_MODEL=~google/gemini-flash-latest
VERSLINE_LLM_PROXY=socks5://127.0.0.1:10808
```

## نکات AvalAI

- شناسه‌ی مدل‌های Gemini (مثل `gemini-3-flash-preview`) خودکار راهنمای `google` را می‌فرستد، مگر اینکه `VERSLINE_LLM_AVALAI_PROVIDER` را خودتان تنظیم کنید.
- هزینه‌ی دقیق هر درخواست با `x-request-id` از مسیر `/user/v1/transactions/lookup` گرفته می‌شود؛ دامنه‌ی `avalapis.ir` هم پشتیبانی می‌شود.
- در شبکه‌های محدود ممکن است برای AvalAI و استعلام هزینه به پروکسی نیاز باشد.
