"""Telegram: login state, chats, channel archive, discussion taqrir, pack, requests answered from a chat."""
from pathlib import Path
from typing import List, Literal, Optional

from versline.bridge.adapter import interactive, run_command
from versline.bridge.registry import F, Params, tool, tr
from versline.bridge.tools._common import force_field, note_field

DATE_HELP = tr("YYYY-MM-DD[ HH:MM], Gregorian or Shamsi (e.g. 1404-07-01).",
               "YYYY-MM-DD[ HH:MM]، میلادی یا شمسی (مثلاً 1404-07-01).")


def _proxy_field():
    return F(None, en="Telegram proxy", fa="پروکسی تلگرام", advanced=True,
             help_en="socks5://host:port or http://host:port", help_fa="socks5://host:port یا http://host:port")


class StatusParams(Params):
    telegram_proxy: Optional[str] = _proxy_field()


@tool("telegram.status", category="telegram", params=StatusParams, needs_llm=False, hidden=True,
      title=tr("Telegram status", "وضعیت تلگرام"),
      description=tr("Whether API credentials are set and which account is logged in.",
                     "آیا اطلاعات API تنظیم شده و با کدام حساب وارد شده‌اید."))
def status(p: StatusParams, ctx):
    from versline.config import settings

    result = {"credentials": bool(settings.telegram.api_id and settings.telegram.api_hash), "account": None, "error": None}
    if not result["credentials"]:
        return result
    try:
        from versline.services.channel_archive.sources.telegram import TelegramSource

        source = TelegramSource(proxy=p.telegram_proxy)
        try:
            result["account"] = source.account_name()
        finally:
            source.close()
    except Exception as exc:
        result["error"] = str(exc)
    return result


class LoginParams(Params):
    api_id: Optional[str] = F(None, en="api_id", fa="api_id", help_en="From https://my.telegram.org (asked if not set).",
                              help_fa="از https://my.telegram.org (اگر تنظیم نشده باشد پرسیده می‌شود).")
    api_hash: Optional[str] = F(None, en="api_hash", fa="api_hash", widget="secret")
    telegram_proxy: Optional[str] = _proxy_field()


@tool("telegram.login", category="telegram", params=LoginParams, needs_llm=False, interactive=True, hidden=True,
      title=tr("Telegram login", "ورود به تلگرام"),
      description=tr("Log in once with your phone number and the code Telegram sends (and 2FA password).",
                     "یک بار با شماره تلفن و کدی که تلگرام می‌فرستد (و رمز دومرحله‌ای) وارد شوید."))
def login(p: LoginParams, ctx):
    import os

    from versline.config import reload_settings

    if p.api_id and p.api_hash:
        if not p.api_id.strip().isdigit():
            raise ValueError("api_id must be a number")
        from versline.commands.telegram import _save_credentials

        _save_credentials(p.api_id.strip(), p.api_hash.strip())
        os.environ["VERSLINE_TELEGRAM_API_ID"] = p.api_id.strip()
        os.environ["VERSLINE_TELEGRAM_API_HASH"] = p.api_hash.strip()
        reload_settings()
    run_command(ctx, "versline.commands.telegram", "login", proxy=p.telegram_proxy)
    return status(StatusParams(telegram_proxy=p.telegram_proxy), ctx)


class LogoutParams(Params):
    pass


@tool("telegram.logout", category="telegram", params=LogoutParams, needs_llm=False, hidden=True,
      title=tr("Telegram logout", "خروج از تلگرام"),
      description=tr("Log out and delete the saved session.", "خروج و حذف نشست ذخیره‌شده."))
def logout(p: LogoutParams, ctx):
    run_command(ctx, "versline.commands.telegram", "logout")
    return {}


KINDS = Literal["user", "bot", "group", "supergroup", "channel"]
LIST_FILE_HELP = tr("Optional .csv, .md or .json file to save the list in.", "فایل اختیاری ‎.csv‎، ‎.md‎ یا ‎.json‎ برای ذخیره‌ی فهرست.")


def _save_list(ctx, rows, output, columns):
    """Rows for the client (no Telethon objects), plus a saved file when asked."""
    from versline.services.telegram_people import COLUMNS, write_rows

    clean = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items() if k != "entity"} for r in rows]
    result = {"rows": clean}
    if output:
        path = write_rows(clean, Path(output).expanduser(), columns or COLUMNS)
        ctx.artifact(path)
        result["output"] = str(path)
    return result


class ChatsParams(Params):
    search: Optional[str] = F(None, en="Search", fa="جستجو", help_en="Title, username or phone.", help_fa="عنوان، نام کاربری یا شماره.")
    limit: Optional[int] = F(None, en="Max chats", fa="حداکثر تعداد", ge=1,
                             help_en="Empty: 100, or all when a date range or a file is given.",
                             help_fa="خالی: ۱۰۰ مورد، یا همه اگر بازه‌ی تاریخ یا فایل داده شود.")
    kinds: List[KINDS] = F([], en="Chat types", fa="نوع گفتگو", widget="tags", help_en="Empty: all. «user» = private chats.",
                           help_fa="خالی: همه. «user» = گفتگوهای شخصی.")
    unread: bool = F(False, en="Unread only", fa="فقط خوانده‌نشده")
    archived: Optional[bool] = F(None, en="Archived", fa="بایگانی‌شده", help_en="Empty: both.", help_fa="خالی: هر دو.", advanced=True)
    since: Optional[str] = F(None, en="Last message from", fa="آخرین پیام از تاریخ", widget="date", help_en=DATE_HELP["en"], help_fa=DATE_HELP["fa"])
    until: Optional[str] = F(None, en="Last message until", fa="آخرین پیام تا تاریخ", widget="date", help_en=DATE_HELP["en"], help_fa=DATE_HELP["fa"])
    output: Optional[str] = F(None, en="Save list as", fa="ذخیره‌ی فهرست", widget="output-file", help_en=LIST_FILE_HELP["en"],
                              help_fa=LIST_FILE_HELP["fa"], accept=[".csv", ".md", ".json"])
    telegram_proxy: Optional[str] = _proxy_field()


@tool("telegram.chats", category="telegram", params=ChatsParams, needs_llm=False, hidden=True,
      title=tr("Telegram chats", "گفتگوهای تلگرام"),
      description=tr("List your chats with the ids to archive, optionally saved as a file.",
                     "فهرست گفتگوها با شناسه‌ی آن‌ها برای بایگانی؛ در صورت تمایل به‌صورت فایل."))
def chats(p: ChatsParams, ctx):
    from versline.commands.telegram import _date_range
    from versline.services.channel_archive.sources.telegram import TelegramSource

    since, until = _date_range(p.since, p.until)
    limit = p.limit if p.limit is not None else (None if (since or until or p.output) else 100)
    with interactive(ctx):
        source = TelegramSource(proxy=p.telegram_proxy)
        try:
            rows = source.iter_dialogs(search=p.search, limit=limit, kinds=set(p.kinds) or None,
                                       unread_only=p.unread, archived=p.archived, since=since, until=until)
        finally:
            source.close()
    result = _save_list(ctx, rows, p.output, ["id", "name", "username", "phone", "type", "last_message", "unread", "archived"])
    result["chats"] = result["rows"]
    return result


class ContactsParams(Params):
    search: Optional[str] = F(None, en="Search", fa="جستجو", help_en="Name, username or phone.", help_fa="نام، نام کاربری یا شماره.")
    mutual: bool = F(False, en="Mutual contacts only", fa="فقط مخاطبین دوطرفه")
    output: Optional[str] = F(None, en="Save list as", fa="ذخیره‌ی فهرست", widget="output-file", help_en=LIST_FILE_HELP["en"],
                              help_fa=LIST_FILE_HELP["fa"], accept=[".csv", ".md", ".json"])
    telegram_proxy: Optional[str] = _proxy_field()


@tool("telegram.contacts", category="telegram", params=ContactsParams, needs_llm=False, hidden=True,
      title=tr("Telegram contacts", "مخاطبین تلگرام"),
      description=tr("List your contacts with name, phone number, username and id.",
                     "فهرست مخاطبین با نام، شماره تلفن، نام کاربری و شناسه."))
def contacts(p: ContactsParams, ctx):
    from versline.services.channel_archive.sources.telegram import TelegramSource

    with interactive(ctx):
        source = TelegramSource(proxy=p.telegram_proxy)
        try:
            rows = source.list_contacts(search=p.search, mutual_only=p.mutual)
        finally:
            source.close()
    return _save_list(ctx, rows, p.output, ["id", "name", "username", "phone", "type", "mutual"])


class MembersParams(Params):
    chat: str = F(..., en="Group", fa="گروه", help_en="@name, a t.me link or a numeric id.", help_fa="‎@name‎، لینک t.me یا شناسه‌ی عددی.")
    search: Optional[str] = F(None, en="Search", fa="جستجو")
    limit: Optional[int] = F(None, en="Max members", fa="حداکثر تعداد", ge=1)
    output: Optional[str] = F(None, en="Save list as", fa="ذخیره‌ی فهرست", widget="output-file", help_en=LIST_FILE_HELP["en"],
                              help_fa=LIST_FILE_HELP["fa"], accept=[".csv", ".md", ".json"])
    telegram_proxy: Optional[str] = _proxy_field()


@tool("telegram.members", category="telegram", params=MembersParams, needs_llm=False, hidden=True,
      title=tr("Group members", "اعضای گروه"),
      description=tr("List the members of a group you belong to.", "فهرست اعضای گروهی که در آن عضو هستید."))
def members(p: MembersParams, ctx):
    from versline.services.channel_archive.sources.telegram import TelegramSource

    with interactive(ctx):
        source = TelegramSource(proxy=p.telegram_proxy)
        try:
            rows = source.list_members(p.chat, search=p.search, limit=p.limit)
        finally:
            source.close()
    return _save_list(ctx, rows, p.output, None)


MEDIA_TYPES = Literal["audio", "voice", "video", "video_note", "photo", "document", "text"]


class ArchiveParams(Params):
    channel: str = F(..., en="Channel", fa="کانال", help_en="@name, a t.me link or a numeric id.",
                     help_fa="‎@name‎، لینک t.me یا شناسه‌ی عددی.")
    output: str = F(..., en="Vault folder", fa="پوشه در والت", widget="output-folder")
    since: Optional[str] = F(None, en="From date", fa="از تاریخ", widget="date", help_en=DATE_HELP["en"], help_fa=DATE_HELP["fa"])
    until: Optional[str] = F(None, en="To date", fa="تا تاریخ", widget="date", help_en=DATE_HELP["en"], help_fa=DATE_HELP["fa"])
    limit: Optional[int] = F(None, en="Max posts", fa="حداکثر تعداد پست", ge=1)
    types: List[MEDIA_TYPES] = F([], en="Media types", fa="نوع رسانه", widget="tags",
                                 help_en="Empty: all.", help_fa="خالی: همه.")
    web: bool = F(False, en="Public web preview (no login)", fa="نسخه‌ی وب عمومی (بدون ورود)",
                  help_en="Public channels only; large audio/video cannot be downloaded.",
                  help_fa="فقط کانال‌های عمومی؛ صوت/ویدیوی بزرگ دانلود نمی‌شود.")
    summary: bool = F(False, en="Add a summary", fa="افزودن خلاصه")
    taqrir: bool = F(False, en="Add a taqrir", fa="افزودن تقریر",
                     help_en="Rewrite the talk as a structured written exposition.",
                     help_fa="سخنرانی به متن مکتوب منظم تبدیل شود.")
    no_transcribe: bool = F(False, en="Skip transcription", fa="بدون پیاده‌سازی")
    keep_media: bool = F(False, en="Keep media in the vault", fa="نگه‌داشتن رسانه در والت",
                         help_en="Save media under attachments/ and embed it.", help_fa="رسانه در attachments ذخیره و در یادداشت درج شود.")
    to_markdown: bool = F(False, en="Convert documents to Markdown", fa="تبدیل اسناد به مارک‌داون",
                          help_en="Each PDF, Word, PowerPoint… file becomes a note under documents/, linked from its post.",
                          help_fa="هر فایل PDF، Word، PowerPoint و… یادداشتی در documents/ می‌شود و از یادداشت پست لینک می‌خورد.")
    ocr: bool = F(False, en="Read scans with AI (OCR)", fa="خواندن اسکن‌ها با هوش مصنوعی (OCR)", advanced=True,
                  help_en="Scanned PDF pages and image files are read by the multimodal model (costs tokens).",
                  help_fa="صفحه‌های اسکن‌شده‌ی PDF و فایل‌های تصویری با مدل چندوجهی خوانده می‌شوند (هزینه دارد).")
    ocr_all: bool = F(False, en="OCR every PDF page", fa="OCR همه‌ی صفحه‌های PDF", advanced=True,
                      help_en="For PDFs whose text comes out garbled (legacy Persian fonts).",
                      help_fa="برای PDFهایی که متنشان به‌هم‌ریخته درمی‌آید (فونت‌های قدیمی فارسی).")
    merge_parts: bool = F(False, en="Merge multi-part posts", fa="ادغام پست‌های چندقسمتی", advanced=True)
    files_only: bool = F(False, en="Files only (no notes, no AI)", fa="فقط فایل‌ها (بدون یادداشت و هوش مصنوعی)", advanced=True)
    ext: Optional[str] = F(None, en="File extensions", fa="پسوند فایل‌ها", help_en="e.g. pdf,docx", advanced=True)
    match: List[str] = F([], en="Keep files matching (regex)", fa="فایل‌های منطبق (regex)", widget="tags", advanced=True)
    exclude: List[str] = F([], en="Drop files matching (regex)", fa="حذف فایل‌های منطبق (regex)", widget="tags", advanced=True)
    max_size: Optional[float] = F(None, en="Max media size (MB)", fa="حداکثر حجم رسانه (MB)", advanced=True)
    output_lang: Optional[str] = F(None, en="Summary/taqrir language", fa="زبان خلاصه/تقریر", advanced=True)
    reuse_transcripts: bool = F(False, en="Reuse transcripts", fa="استفاده‌ی دوباره از متن‌های پیاده‌شده", advanced=True)
    dry_run: bool = F(False, en="Preview only", fa="فقط پیش‌نمایش", help_en="List matching posts; nothing is saved.",
                      help_fa="فقط فهرست پست‌ها؛ چیزی ذخیره نمی‌شود.")
    pack: bool = F(False, en="Build the pack afterwards", fa="ساخت بسته‌ی کامل پس از بایگانی", advanced=True)
    telegram_proxy: Optional[str] = _proxy_field()
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("telegram.archive", category="telegram", params=ArchiveParams, interactive=True,
      title=tr("Archive a Telegram channel", "بایگانی کانال تلگرام"),
      description=tr("Save a channel's posts in a date range as notes, with transcripts, summaries and taqrir.",
                     "پست‌های یک کانال را در بازه‌ی تاریخی به‌صورت یادداشت، همراه با متن پیاده‌شده، خلاصه و تقریر ذخیره می‌کند."))
def archive(p: ArchiveParams, ctx):
    out = Path(p.output).expanduser()
    produced = run_command(
        ctx, "versline.commands.telegram", "archive", outputs=[] if p.dry_run else [out],
        channel=p.channel, output=out, since=p.since, until=p.until, limit=p.limit,
        types=",".join(p.types) or None, web=p.web, add_summary=p.summary, add_taqrir=p.taqrir,
        no_transcribe=p.no_transcribe, keep_media=p.keep_media, merge_parts=p.merge_parts, files_only=p.files_only,
        to_markdown=p.to_markdown, ocr=p.ocr, ocr_all=p.ocr_all,
        ext=p.ext, match=list(p.match) or None, exclude=list(p.exclude) or None, max_size=p.max_size,
        output_lang=p.output_lang, reuse_transcripts=p.reuse_transcripts, dry_run=p.dry_run, make_pack=p.pack,
        telegram_proxy=p.telegram_proxy, note=p.note, force=p.force,
    )
    return {"outputs": [str(x) for x in produced], "output_dir": str(out)}


class TaqrirParams(Params):
    chat: str = F(..., en="Chat", fa="گفتگو", help_en="@user, @group, a t.me link, a numeric id or 'me'.",
                  help_fa="‎@user‎، ‎@group‎، لینک t.me، شناسه‌ی عددی یا me.")
    output: str = F(..., en="Vault folder", fa="پوشه در والت", widget="output-folder")
    since: Optional[str] = F(None, en="From date", fa="از تاریخ", widget="date", help_en=DATE_HELP["en"], help_fa=DATE_HELP["fa"])
    until: Optional[str] = F(None, en="To date", fa="تا تاریخ", widget="date", help_en=DATE_HELP["en"], help_fa=DATE_HELP["fa"])
    style: Literal["descriptive", "claims", "both"] = F("both", en="Style", fa="سبک", choices={
        "descriptive": tr("Descriptive prose", "توصیفی"),
        "claims": tr("Propositions with evidence", "گزاره‌ها با ادله"),
        "both": tr("Both", "هر دو")})
    attribute: bool = F(False, en="Name participants", fa="نام بردن از شرکت‌کنندگان")
    instruction: Optional[str] = F(None, en="Focus / guidance", fa="محور یا راهنمایی", widget="textarea")
    output_lang: Optional[str] = F(None, en="Language", fa="زبان", advanced=True)
    no_transcribe: bool = F(False, en="Skip voice/video", fa="بدون پیاده‌سازی صوت/ویدیو", advanced=True)
    no_documents: bool = F(False, en="Skip documents", fa="بدون خواندن اسناد", advanced=True)
    no_images: bool = F(False, en="Skip images", fa="بدون خواندن تصاویر", advanced=True)
    no_log: bool = F(False, en="No message log note", fa="بدون یادداشت گزارش پیام‌ها", advanced=True)
    limit: Optional[int] = F(None, en="Max messages", fa="حداکثر پیام", ge=1, advanced=True)
    dry_run: bool = F(False, en="Preview only", fa="فقط پیش‌نمایش")
    telegram_proxy: Optional[str] = _proxy_field()
    note: Optional[str] = note_field()
    force: bool = force_field()


@tool("telegram.taqrir", category="telegram", params=TaqrirParams, interactive=True,
      title=tr("Taqrir of a discussion", "تقریر مباحثه"),
      description=tr("Write a taqrir of a chat's discussions between two dates (voice, documents and images included).",
                     "تقریر مباحثات یک گفتگو بین دو تاریخ (همراه با صوت‌ها، اسناد و تصاویر)."))
def taqrir(p: TaqrirParams, ctx):
    out = Path(p.output).expanduser()
    produced = run_command(
        ctx, "versline.commands.telegram", "taqrir", outputs=[] if p.dry_run else [out],
        chat=p.chat, output=out, since=p.since, until=p.until, style=p.style, attribute=p.attribute,
        instruction=p.instruction, output_lang=p.output_lang, no_transcribe=p.no_transcribe,
        no_documents=p.no_documents, no_images=p.no_images, no_log=p.no_log, limit=p.limit, dry_run=p.dry_run,
        telegram_proxy=p.telegram_proxy, note=p.note, force=p.force,
    )
    return {"outputs": [str(x) for x in produced], "output_dir": str(out)}


class PackParams(Params):
    archive_dir: str = F(..., en="Archive folder", fa="پوشه‌ی بایگانی", widget="folder",
                         help_en="A folder made by the channel archive.", help_fa="پوشه‌ای که بایگانی کانال ساخته است.")
    output: Optional[str] = F(None, en="Pack folder", fa="پوشه‌ی بسته", widget="output-folder", output="{path}_pack")
    force: bool = force_field()


@tool("telegram.pack", category="telegram", params=PackParams, needs_llm=False,
      title=tr("Pack an archive", "بسته‌ی کامل بایگانی"),
      description=tr("Build a book, per-post Word/PDF files, a catalog and a ZIP from an archive folder.",
                     "از یک پوشه‌ی بایگانی، کتاب، فایل Word/PDF هر پست، فهرست و فایل ZIP می‌سازد."))
def pack(p: PackParams, ctx):
    output = Path(p.output).expanduser() if p.output else None
    produced = run_command(ctx, "versline.commands.telegram", "pack", outputs=[output] if output else [],
                           archive_dir=p.archive_dir, output=output, force=p.force)
    return {"outputs": [str(x) for x in produced]}


class RequestsParams(Params):
    chat: str = F("me", en="Requests chat", fa="گفتگوی درخواست‌ها",
                  help_en="Where you keep talks and reply to them: 'me' (Saved Messages), @name, a link or a numeric id.",
                  help_fa="جایی که فایل‌ها را نگه می‌دارید و به آن‌ها ریپلای می‌کنید: me (پیام‌های ذخیره‌شده)، ‎@name‎، لینک یا شناسه‌ی عددی.")
    output: str = F(..., en="Vault folder", fa="پوشه در والت", widget="output-folder")
    clip: bool = F(True, en="Cut audio clips", fa="بریدن تکه‌ی صوتی")
    refine: bool = F(True, en="Re-transcribe found passages", fa="پیاده‌سازی دوباره‌ی بخش‌های پیداشده")
    reply: bool = F(True, en="Reply in Telegram", fa="پاسخ در تلگرام",
                    help_en="Off: only write notes in the vault.", help_fa="خاموش: فقط یادداشت در والت نوشته شود.")
    lookback_days: int = F(3, en="First run: look back (days)", fa="اجرای اول: چند روز قبل", ge=1, advanced=True,
                           help_en="Later runs continue from the last message read.",
                           help_fa="اجراهای بعدی از آخرین پیام خوانده‌شده ادامه می‌دهند.")
    limit: Optional[int] = F(None, en="Max messages to read", fa="حداکثر پیام برای خواندن", ge=1, advanced=True)
    output_lang: Optional[str] = F(None, en="Language", fa="زبان", advanced=True)
    skip_blocked: bool = F(False, en="Skip blocked chunks", fa="رد شدن از تکه‌های مسدودشده", advanced=True)
    dry_run: bool = F(False, en="Preview only", fa="فقط پیش‌نمایش",
                      help_en="List the requests found; nothing is answered.", help_fa="فقط فهرست درخواست‌ها؛ به چیزی پاسخ داده نمی‌شود.")
    telegram_proxy: Optional[str] = _proxy_field()


@tool("telegram.requests", category="telegram", params=RequestsParams, interactive=True,
      title=tr("Answer Telegram requests", "پاسخ به درخواست‌های تلگرام"),
      description=tr("Answer your replies to talks in a chat: a taqrir of the talk, or the passages you describe, "
                     "with their times and audio clips.",
                     "به ریپلای‌های شما روی فایل‌های یک گفتگو پاسخ می‌دهد: تقریر کل فایل، یا پیدا کردن نکته‌هایی که توصیف "
                     "کرده‌اید همراه با زمان و تکه‌ی صوتی."))
def requests(p: RequestsParams, ctx):
    from versline.config import settings
    from versline.services.channel_archive.llm import TextLLM
    from versline.services.channel_archive.sources.telegram import TelegramSource
    from versline.services.pricing import cost_summary
    from versline.services.telegram_requests import (
        RequestOptions, RequestProcessor, RequestState, default_state_path,
    )
    from versline.services.transcription import AudioTranscriber

    out = Path(p.output).expanduser()
    transcriber = AudioTranscriber()

    def factory(note: str):
        sub = AudioTranscriber(user_note=note)
        sub.tracker = transcriber.tracker
        return sub

    def progress(message: str) -> None:
        ctx.check_cancel()
        ctx.progress(None, None, message)

    options = RequestOptions(
        output_dir=out, temp_dir=Path(settings.temp_directory) / "telegram-requests", lookback_days=p.lookback_days,
        limit=p.limit, clip=p.clip, refine=p.refine, reply=p.reply, output_lang=p.output_lang or "",
        skip_blocked=p.skip_blocked, dry_run=p.dry_run,
    )
    with interactive(ctx):
        try:
            source = TelegramSource(proxy=p.telegram_proxy)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
        try:
            processor = RequestProcessor(source, TextLLM(transcriber.tracker), transcriber, factory, options,
                                         RequestState(default_state_path()), progress)
            summary = processor.run(p.chat)
        finally:
            source.close()
    for path in summary.outputs:
        ctx.artifact(path)
    if summary.processed:
        ctx.cost(cost_summary(transcriber.tracker, api_key=settings.llm.api_key))
    for error in summary.errors:
        ctx.log(error, level="error")
    return {
        "outputs": [str(x) for x in summary.outputs],
        "processed": summary.processed,
        "failed": summary.failed,
        "pending": summary.pending,
        "warnings": summary.warnings,
        "output_dir": str(out),
    }
