<div dir="rtl">

# ورس‌لاین (Versline)

**ابزار هوشمند تبدیل صوت و ویدیو به متن، ترجمه، خلاصه‌سازی و بایگانی کانال‌های تلگرام**

ورس‌لاین با کمک هوش مصنوعی کارهای زیر را برای شما انجام می‌دهد:

- 🎙️ **پیاده‌سازی متن** فایل‌های صوتی و ویدیویی (فایل یا لینک)
- 🌐 **ترجمه‌ی** متن و سند
- 📄 **خلاصه‌سازی** مقاله، کتاب و جزوه
- 📣 **بایگانی کانال تلگرام** به‌صورت یادداشت‌های Obsidian (با متن پیاده‌شده‌ی صوت‌ها، خلاصه و تقریر)
- ❓ ساخت **سؤال و فلش‌کارت**، 🎞️ ساخت **اسلاید**، 🧩 **کدگذاری کیفی** و 🎓 **نگارش فصل یافته‌ها**

> برای استفاده به یک **کلید API** از یکی از این سرویس‌ها نیاز دارید: Google (Gemini)، OpenAI، OpenRouter یا AvalAI.

---

## ۱. نصب

### ویندوز

برنامه‌ی **PowerShell** را باز کنید، این خط را کپی و اجرا کنید:

```powershell
irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
```

(حدود ۱۵۰ مگابایت دانلود می‌شود. نیازی به نصب پایتون نیست و ffmpeg هم همراه برنامه است.)

### مک و لینوکس

```sh
curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh
```

### مهم

بعد از نصب، ترمینال را **ببندید و دوباره باز کنید**؛ سپس بررسی کنید:

```sh
versline --version
```

---

## ۲. تنظیم اولیه (فقط یک بار)

```sh
versline init
```

برنامه از شما می‌پرسد:

1. از کدام سرویس استفاده می‌کنید؟ (Google، OpenAI، OpenRouter، AvalAI یا سازگار با OpenAI)
2. کلید API شما چیست؟ (هنگام تایپ دیده نمی‌شود)
3. کدام مدل؟ (می‌توانید فقط Enter بزنید تا مدل پیشنهادی انتخاب شود)
4. پروکسی دارید؟ (اختیاری، مثلاً `socks5://127.0.0.1:10808`)

تنظیمات شما ذخیره می‌شود و دیگر لازم نیست دوباره وارد کنید. برای دیدن آن‌ها: `versline config`

---

## ۳. چند مثال آماده (کپی و اجرا کنید)

### 🎙️ تبدیل صوت یا ویدیو به متن

```sh
versline transcribe فایل.mp3
versline transcribe "https://example.com/lecture.mp4"
```

نتیجه در پوشه‌ی `output` ذخیره می‌شود. اگر کار نیمه‌کاره قطع شد، همان دستور را دوباره بزنید؛ از ادامه کار می‌کند.

### 🌐 ترجمه

```sh
versline translate مقاله.md --lang English
```

### 📄 خلاصه‌سازی

```sh
versline summarize جزوه.pdf
versline summarize جزوه.pdf --mode outline        # فقط سرفصل‌ها
versline summarize paper.pdf --output-lang Persian # خلاصه‌ی فارسی از متن انگلیسی
```

### 📣 بایگانی کانال تلگرام

بدون نیاز به ورود به حساب (برای کانال‌های **عمومی**):

```sh
# اول ببینید در این بازه چه پست‌هایی هست (چیزی ذخیره نمی‌شود)
versline telegram archive @نام_کانال --web --since 2026-03-01 --dry-run

# بایگانی در پوشه‌ی Obsidian شما
versline telegram archive @نام_کانال --web --since 2026-03-01 -o ~/Vault/کانال
```

برای کانال خصوصی یا برای دانلود فایل‌های صوتی بزرگ، یک بار با حساب خود وارد شوید:

```sh
versline telegram login
versline telegram archive @نام_کانال --since 1404-07-01 --summary --taqrir -o ~/Vault/کانال
```

- `--summary` یک خلاصه به بالای هر یادداشت اضافه می‌کند.
- `--taqrir` سخنرانی را به یک متن مکتوب منظم تبدیل می‌کند.
- تاریخ را می‌توانید شمسی بنویسید (مثل `1404-07-01`).
- اگر اجرا قطع شد، دوباره همان دستور را بزنید؛ پست‌های تمام‌شده تکرار نمی‌شوند.

### 🔄 به‌روزرسانی

```sh
versline update
```

---

## ۴. همه‌ی دستورها

| دستور | کار |
| :--- | :--- |
| `versline init` | تنظیم اولیه (سرویس و کلید API) |
| `versline config` | نمایش تنظیمات ذخیره‌شده |
| `versline update` | به‌روزرسانی برنامه |
| `versline transcribe` | صوت/ویدیو ← متن |
| `versline translate` | ترجمه‌ی فایل |
| `versline summarize` | خلاصه‌سازی |
| `versline telegram` | بایگانی کانال تلگرام |
| `versline qude` | ساخت سؤال و فلش‌کارت (CSV، Anki، HTML) |
| `versline qualcode` | کدگذاری کیفی مصاحبه‌ها |
| `versline research` | نگارش مرحله‌ای فصل یافته‌ها |
| `versline slides` | ساخت اسلاید از Markdown |

برای راهنمای هر دستور بنویسید: `versline <دستور> --help` (مثلاً `versline transcribe --help`).

---

## ۵. مشکلی پیش آمد؟

| مشکل | راه‌حل |
| :--- | :--- |
| `versline` پیدا نمی‌شود | ترمینال را ببندید و **دوباره** باز کنید |
| خطای کلید API | دوباره `versline init` را اجرا کنید |
| به سرویس هوش مصنوعی وصل نمی‌شود | پروکسی بدهید: `--proxy socks5://127.0.0.1:10808` یا آن را در `versline init` وارد کنید |
| متن فارسی در ویندوز به‌هم‌ریخته است | فقط نمایش کنسول است؛ فایل خروجی را با ویرایشگر (مثل Notepad++ یا VS Code) باز کنید |
| تلگرام می‌گوید «Not logged in» | `versline telegram login` را بزنید، یا برای کانال عمومی `--web` اضافه کنید |
| کار طولانی قطع شد | همان دستور را دوباره اجرا کنید؛ ادامه می‌یابد |

مشکلات بیشتر: [رفع اشکال](docs/fa/troubleshooting.md)

---

## ۶. مستندات کامل

| | فارسی | English |
| :--- | :--- | :--- |
| فهرست | [docs/fa/index.md](docs/fa/index.md) | [docs/en/index.md](docs/en/index.md) |
| نصب | [نصب](docs/fa/installation.md) | [Installation](docs/en/installation.md) |
| تنظیمات | [تنظیمات](docs/fa/configuration.md) | [Configuration](docs/en/configuration.md) |
| دستورها | [مرجع دستورها](docs/fa/commands.md) | [Command reference](docs/en/commands.md) |
| تلگرام | [بایگانی تلگرام](docs/fa/telegram.md) | [Telegram archive](docs/en/telegram.md) |
| برنامه‌نویسان | [کتابخانه و MCP](docs/fa/library.md) · [معماری](docs/fa/architecture.md) | [Library & MCP](docs/en/library.md) · [Architecture](docs/en/architecture.md) |

---

مجوز: MIT · ساخته‌شده توسط [Miroverse Solutions](https://github.com/miroverse-solutions)

</div>
