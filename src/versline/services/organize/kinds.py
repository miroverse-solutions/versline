"""File kind detection by extension (and a few well-known junk names)."""
from __future__ import annotations

from typing import Dict

from versline.services.organize.normalize import split_ext

KINDS = ("book", "document", "web", "audio", "video", "image", "archive", "software", "font", "junk", "other")

_KIND_EXTS = {
    "book": "pdf epub djvu djv mobi azw azw3 chm fb2 cbz cbr",
    "document": "doc docx docm rtf odt txt md xls xlsx xlsm csv ppt pptx pps ppsx odp ods one mmap xmind mm "
                "enl ris bib tex vsd vsdx pub",
    "web": "htm html mht mhtml css js xml json",
    "audio": "mp3 wav wma m4a aac ogg oga opus flac amr 3ga aiff aif ape mka",
    "video": "mp4 mkv avi wmv mov flv ts 3gp webm mpg mpeg vob m4v rm rmvb asf f4v",
    "image": "jpg jpeg jfif jpe png gif bmp tif tiff webp heic heif psd svg ico",
    "archive": "zip rar 7z tar gz tgz bz2 xz iso z01 z02 r00 r01 001",
    "software": "exe msi dll sys ocx apk jar bat cmd com cab inf msp appx msix deb rpm dmg so",
    "font": "ttf otf ttc fon fnt woff woff2",
    "junk": "tmp temp lnk crdownload partial ~tmp",
}

EXT_KIND: Dict[str, str] = {ext: kind for kind, exts in _KIND_EXTS.items() for ext in exts.split()}
JUNK_NAMES = {"thumbs.db", "ehthumbs.db", "desktop.ini", ".ds_store", "folder.jpg.tmp"}
SOFTWARE_EXTS = {ext for ext, kind in EXT_KIND.items() if kind == "software"}


def file_ext(name: str) -> str:
    return split_ext(name)[1].lower()


def classify_kind(name: str) -> str:
    low = name.lower()
    if low in JUNK_NAMES or low.startswith("~$") or low.startswith("._"):
        return "junk"
    return EXT_KIND.get(file_ext(name), "other")
