"""Mapping rules (``rules.txt``) and the destination taxonomy (``taxonomy.txt``).

rules.txt — one rule per line, ``#`` starts a comment::

    @dest_root   مرتب                                  # destination folder, relative to the drive root
    @default     ۹-بایگانی خام                           # unmatched files → <default>/<source label>/<path>
    @root_priority کتابخانه الکترونیکی | هارد 64 گیگا بایت   # which copy of a duplicate to keep first
    @media       ۱-کتابخانه => ۲-صوت و تصویر              # audio/video whose destination starts with the left side
    @media_kinds audio video                            # kinds that are moved instead of copied
    @media_folder_ratio 0.8                             # other files in a folder this media-heavy follow the media
    کتابخانه الکترونیکی/اصول و فقه => ۱-کتابخانه/اصول و فقه

A rule's left side is a source path prefix ``<source label>/<folder or file>``; the longest matching prefix wins
and the rest of the path is kept under the destination. Matching ignores Arabic/Persian ي/ك differences and
extra spaces. A rule naming a single file puts that file directly into the destination folder.

taxonomy.txt — one destination folder per line, optionally ``| description``. Used to warn about rules that point
outside the agreed structure (and, later, as the category list for AI classification).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from versline.services.organize.normalize import normalize_text

ARROW = "=>"


@dataclass
class Rule:
    prefix: str
    dest: str
    line: int

    @property
    def label(self) -> str:
        return f"{self.line}: {self.prefix}"


@dataclass
class RuleSet:
    rules: List[Rule] = field(default_factory=list)
    dest_root: str = "مرتب"
    default: str = "۹-بایگانی خام"
    root_priority: List[str] = field(default_factory=list)
    media_map: List[Tuple[str, str]] = field(default_factory=list)
    media_kinds: Tuple[str, ...] = ("audio", "video")
    media_folder_ratio: float = 0.8
    errors: List[str] = field(default_factory=list)
    _index: Dict[str, Rule] = field(default_factory=dict, repr=False)

    def build_index(self) -> None:
        self._index = {_key(rule.prefix): rule for rule in self.rules}

    def match(self, label: str, relpath: str) -> Tuple[Optional[Rule], str]:
        """Longest rule matching ``label/relpath`` and the remaining path to keep under its destination."""
        if not self._index and self.rules:
            self.build_index()
        parts = [label] + relpath.split("/")
        for depth in range(len(parts), 0, -1):
            rule = self._index.get(_key("/".join(parts[:depth])))
            if rule:
                rest = "/".join(parts[depth:]) or parts[-1]  # a single-file rule keeps the file name
                return rule, rest
        return None, relpath

    def media_dest(self, dest: str) -> str:
        """Re-root a destination for media (``۱-کتابخانه/x`` → ``۲-صوت و تصویر/x``); longest prefix wins."""
        best = None
        for source, target in self.media_map:
            if dest == source or dest.startswith(source + "/"):
                if best is None or len(source) > len(best[0]):
                    best = (source, target)
        if not best:
            return dest
        return best[1] + dest[len(best[0]):]

    def priority(self, label: str) -> int:
        try:
            return self.root_priority.index(label)
        except ValueError:
            return len(self.root_priority)


def _key(path: str) -> str:
    return "/".join(normalize_text(part) for part in path.strip().strip("/").split("/"))


def _clean_path(text: str) -> str:
    return "/".join(part.strip() for part in text.strip().replace("\\", "/").strip("/").split("/") if part.strip())


def parse_rules(text: str) -> RuleSet:
    ruleset = RuleSet()
    seen: Dict[str, int] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("@"):
            name, _, value = line[1:].partition(" ")
            name, value = name.strip().lower(), value.strip()
            if name == "dest_root":
                ruleset.dest_root = _clean_path(value)
            elif name == "default":
                ruleset.default = _clean_path(value)
            elif name == "root_priority":
                ruleset.root_priority = [_clean_path(v) for v in value.split("|") if v.strip()]
            elif name == "media":
                left, arrow, right = value.partition(ARROW)
                if not arrow:
                    ruleset.errors.append(f"line {number}: @media needs 'from => to'")
                    continue
                ruleset.media_map.append((_clean_path(left), _clean_path(right)))
            elif name == "media_kinds":
                ruleset.media_kinds = tuple(value.split())
            elif name == "media_folder_ratio":
                try:
                    ruleset.media_folder_ratio = float(value)
                except ValueError:
                    ruleset.errors.append(f"line {number}: invalid number {value!r}")
            else:
                ruleset.errors.append(f"line {number}: unknown directive @{name}")
            continue
        left, arrow, right = line.partition(ARROW)
        if not arrow or not left.strip() or not right.strip():
            ruleset.errors.append(f"line {number}: expected 'source/prefix => destination/folder'")
            continue
        prefix, dest = _clean_path(left), _clean_path(right)
        key = _key(prefix)
        if key in seen:
            ruleset.errors.append(f"line {number}: duplicate rule for {prefix!r} (first on line {seen[key]})")
            continue
        seen[key] = number
        ruleset.rules.append(Rule(prefix, dest, number))
    ruleset.build_index()
    return ruleset


def load_rules(path: Path) -> RuleSet:
    return parse_rules(Path(path).read_text(encoding="utf-8-sig"))


def load_taxonomy(path: Path) -> List[str]:
    if not Path(path).is_file():
        return []
    entries = []
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw.split("#", 1)[0].split("|", 1)[0].strip()
        if line:
            entries.append(_clean_path(line))
    return entries


def outside_taxonomy(dest: str, taxonomy: List[str], depth: int = 2) -> bool:
    """True when the first ``depth`` levels of ``dest`` are not a folder (or parent folder) in the taxonomy."""
    if not taxonomy:
        return False
    head = _key("/".join(dest.split("/")[:depth]))
    keys = [_key(entry) for entry in taxonomy]
    return not any(k == head or k.startswith(head + "/") or head.startswith(k + "/") for k in keys)
