try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    try:
        __version__ = _pkg_version("versline")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

_LAZY_EXPORTS = {
    "AudioTranscriber": ("versline.services.transcription", "AudioTranscriber"),
    "TextTranslator": ("versline.services.translation", "TextTranslator"),
    "download_file": ("versline.services.network", "download_file"),
    "QualitativeCoder": ("versline.services.qualitative_coding", "QualitativeCoder"),
    "MarkdownSlideDeckGenerator": ("versline.services.slides", "MarkdownSlideDeckGenerator"),
    "settings": ("versline.config", "settings"),
    "reload_settings": ("versline.config", "reload_settings"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'versline' has no attribute {name!r}")

    module_name, attr_name = _LAZY_EXPORTS[name]
    module = __import__(module_name, fromlist=[attr_name])
    return getattr(module, attr_name)
