# مستندات ورس‌لاین (Versline)

[English](../en/index.md) · **فارسی**

ورس‌لاین یک ابزار خط فرمان و کتابخانه‌ی پایتون از Miroverse Solutions است که با کمک مدل‌های زبانی بزرگ (LLM)، صوت، تصویر و اسناد را به متن مفید تبدیل می‌کند. نسخه‌ی فعلی: **۱.۰.۴** (مجوز MIT).

## چه کارهایی می‌کند

| دستور | کاربرد |
| :--- | :--- |
| `transcribe` | تبدیل صوت/ویدیو (فایل یا لینک) به متن، با امکان زمان‌بندی |
| `translate` | ترجمه‌ی فایل متنی/سند |
| `summarize` | خلاصه‌سازی فایل (طرح کلی، تفصیلی، اسلاید؛ حالت آموزشی اختیاری) |
| `qude` | تولید سؤال چندگزینه‌ای/تشریحی و خروجی CSV، Anki و HTML |
| `qualcode` | کدگذاری کیفی (تماتیک، زمینه‌ای، محتوایی، چارچوبی، کلایزی) |
| `research` | نگارش مرحله‌ای فصل «یافته‌ها» |
| `slides` | ساخت اسلاید HTML/TypeScript از Markdown |
| `telegram` | بایگانی کانال تلگرام به‌صورت یادداشت‌های Obsidian (با متن پیاده‌شده، خلاصه و تقریر) |
| `init`، `config`، `update` | تنظیم اولیه، نمایش تنظیمات ذخیره‌شده، به‌روزرسانی |

سرویس‌دهنده‌های پشتیبانی‌شده: **Google (Gemini)، OpenAI، OpenRouter، AvalAI و هر سرویس سازگار با OpenAI**.

## فهرست

1. [نصب](installation.md)
2. [تنظیمات](configuration.md)
3. [مرجع دستورها](commands.md)
4. [بایگانی کانال تلگرام](telegram.md)
5. [کتابخانه‌ی پایتون و سرور MCP](library.md)
6. [معماری و توسعه](architecture.md)
7. [رفع اشکال](troubleshooting.md)

## شروع سریع

```sh
# ۱. نصب (برای ویندوز به installation.md نگاه کنید)
curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh

# ۲. تنظیم یک‌باره: انتخاب سرویس و ذخیره‌ی کلید API
versline init

# ۳. استفاده
versline transcribe interview.mp3
versline translate article.md --lang English
versline summarize paper.pdf --mode outline
```

خروجی‌ها به‌طور پیش‌فرض در پوشه‌ی `output/` کنار محل اجرا ذخیره می‌شوند (`VERSLINE_OUTPUT_DIRECTORY`).
