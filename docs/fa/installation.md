# نصب

[فهرست](index.md) · [English](../en/installation.md) · **فارسی**

## کاربران عادی

### ویندوز (روش پیشنهادی)

PowerShell را باز کنید و این دستور را اجرا کنید:

```powershell
irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
```

این اسکریپت فایل `versline-windows-x64.zip` را از آخرین انتشار GitHub دانلود می‌کند (حدود ۱۵۰ مگابایت؛ با `curl.exe` و نوار پیشرفت، و در صورت نبود آن با `Invoke-WebRequest`)، در `%LOCALAPPDATA%\Versline` استخراج می‌کند (نسخه‌ی قبلی جایگزین می‌شود و مسیر فایل‌ها در برابر zip-slip بررسی می‌شود) و آن پوشه را به `PATH` کاربر اضافه می‌کند. نسخه‌ی مستقل است: **نیازی به پایتون، uv یا PyPI نیست** و ffmpeg هم همراه آن است.

### مک / لینوکس

```sh
curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh
```

اگر [uv](https://docs.astral.sh/uv/) نصب نباشد نصب می‌شود؛ سپس `uv tool install --force --python 3.12 <wheel>` با فایل wheel آخرین انتشار و بعد `uv tool update-shell` اجرا می‌شود.

### بعد از نصب

ترمینال را ببندید و یک ترمینال **جدید** باز کنید:

```sh
versline --version
versline init      # انتخاب سرویس، کلید API و مدل (فقط یک بار)
```

ffmpeg خودکار پیدا می‌شود (بخش [تنظیمات](configuration.md#media)). در کنسول ویندوز ممکن است متن فارسی درست نمایش داده نشود؛ فایل‌های خروجی را در یک ویرایشگر باز کنید.

### به‌روزرسانی

```sh
versline update
```

ورس‌لاین حداکثر روزی یک بار (فقط در ترمینال تعاملی) وجود نسخه‌ی جدید را در GitHub بررسی و اطلاع می‌دهد. در ویندوز `update` یک پنجره‌ی جدید PowerShell باز می‌کند و `install.ps1` را دوباره اجرا می‌کند؛ در سیستم‌های دیگر `uv tool install --force` اجرا می‌شود (نیازمند `uv`).

### حذف

- ویندوز: پوشه‌ی `%LOCALAPPDATA%\Versline` را پاک کنید و آن را از `PATH` کاربر حذف کنید.
- مک / لینوکس: `uv tool uninstall versline`.
- در صورت تمایل پوشه‌ی تنظیمات کاربر را هم پاک کنید ([محل تنظیمات](configuration.md#where-settings-live)).

## نصب از سورس

```sh
git clone https://github.com/miroverse-solutions/versline.git
cd versline
pip install .
```

نیازمند Python 3.9 یا بالاتر (انتشارها با Python 3.12 ساخته و آزمایش می‌شوند).

## محیط توسعه

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # معادل: make dev
make test                    # python -m pytest tests -q
```

## ساخت بسته‌ی wheel

```sh
make build                   # python -m build، خروجی در dist/
pip install dist/versline-*.whl
```

## تکمیل خودکار دستورها

```sh
versline --install-completion
```

<a id="releasing-maintainers"></a>
## انتشار (برای نگهدارندگان)

`make release` آزمون‌ها را اجرا می‌کند، درخت git باید تمیز و push شده باشد، سپس workflow به نام *Manual Draft Release* در GitHub Actions را اجرا می‌کند (`make release-draft` پیش‌نویس می‌سازد). این workflow روی Ubuntu/Windows/macOS آزمون می‌گیرد، بسته‌ی PyInstaller ویندوز (همراه ffmpeg) را می‌سازد و wheel، sdist و zip ویندوز را با تگ `vX.Y.Z` (از `pyproject.toml`) منتشر می‌کند.
