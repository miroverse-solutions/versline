"""Build a self-contained Versline folder with PyInstaller (run from the repo root)."""
import PyInstaller.__main__
from static_ffmpeg.run import get_or_fetch_platform_executables_else_raise

# Fetch ffmpeg now so it ships inside the bundle instead of downloading silently on first use.
get_or_fetch_platform_executables_else_raise()

COLLECT_ALL = [
    "versline", "markitdown", "static_ffmpeg", "genanki", "pptx", "docx",
    "pdfplumber", "pymupdf", "magika", "mcp", "google.genai", "openpyxl",
]

args = ["packaging/entry.py", "--name", "versline", "--onedir", "--noconfirm", "--clean",
        "--distpath", "dist-bin", "--workpath", "build-bin", "--specpath", "build-bin"]
for pkg in COLLECT_ALL:
    args += ["--collect-all", pkg]
for pkg in ("pydantic", "pydantic_settings", "loguru", "tiktoken", "telethon"):
    args += ["--collect-submodules", pkg]
PyInstaller.__main__.run(args)
