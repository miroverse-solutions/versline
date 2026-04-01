from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from versline.services.rag.base import BasePreprocessor, Document


class MarkdownPreprocessor(BasePreprocessor):
    def preprocess(self, file_path: str, **kwargs) -> List[Document]:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        return [
            Document(
                text=text,
                metadata={
                    "source": str(path),
                    "input_type": "markdown",
                    "file_name": path.name,
                },
            )
        ]


DEFAULT_EXTENSION_TO_INPUT_TYPE: Dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "markdown",
}
