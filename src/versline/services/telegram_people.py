"""Telegram people lists: write contacts/chats/members to CSV/MD/JSON and read recipient lists back."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

COLUMNS = ["id", "name", "username", "phone", "type"]

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_ALIASES = {
    "id": {"id", "user_id", "chat_id", "telegram_id", "شناسه", "آیدی عددی"},
    "username": {"username", "user", "telegram", "tg", "handle", "آیدی", "یوزرنیم", "نام کاربری"},
    "phone": {"phone", "mobile", "tel", "telephone", "number", "تلفن", "شماره", "موبایل", "شماره تلفن", "همراه"},
    "name": {"name", "full_name", "نام", "نام و نام خانوادگی"},
}
# Reference columns in priority order: the first non-empty one identifies the recipient.
_REF_ORDER = ["id", "username", "phone", "name"]


@dataclass
class Recipient:
    ref: str  # the raw value used to find the person
    kind: str  # id | username | phone | name
    name: str = ""
    fields: Dict[str, str] = field(default_factory=dict)  # every CSV column, for {placeholders}

    @property
    def label(self) -> str:
        return self.name or self.ref


def normalize_phone(value: str) -> str:
    """'+989121234567' for any spelling of an Iranian-style or international number; '' when there are no digits."""
    text = (value or "").translate(_DIGITS)
    plus = text.strip().startswith("+") or text.strip().startswith("00")
    digits = re.sub(r"\D", "", text)
    if digits.startswith("00"):
        digits = digits[2:]
    return ("+" if plus and digits else "") + digits


def phone_key(value: str) -> str:
    """Last 10 digits, so 0912…, 98912… and +98912… are the same number."""
    digits = re.sub(r"\D", "", normalize_phone(value))
    return digits[-10:] if len(digits) >= 7 else digits


def classify(value: str) -> str:
    v = (value or "").strip()
    if v.startswith("@") or re.match(r"^(?:https?://)?t\.me/[A-Za-z0-9_]+", v):
        return "username"
    digits = re.sub(r"\D", "", v.translate(_DIGITS))
    if digits and re.fullmatch(r"[+\d\s()\-–۰-۹٠-٩]+", v):
        if v.startswith(("+", "00", "0")) and len(digits) >= 8:
            return "phone"
        if re.fullmatch(r"-?\d+", v.translate(_DIGITS)):
            return "id"
        return "phone" if len(digits) >= 8 else "name"
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", v):
        return "username"
    return "name"


def _clean_username(value: str) -> str:
    v = value.strip()
    m = re.match(r"^(?:https?://)?t\.me/([A-Za-z0-9_]+)", v)
    return (m.group(1) if m else v).lstrip("@")


# -- writing ---------------------------------------------------------------


def write_rows(rows: Iterable[dict], path: Path, columns: Optional[List[str]] = None) -> Path:
    """Write rows as CSV (UTF-8 with BOM, for Excel), Markdown table or JSON, chosen by the extension."""
    rows = list(rows)
    columns = columns or COLUMNS
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".json":
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    elif suffix in (".md", ".markdown"):
        def cell(v):
            return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")

        lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
        lines += ["| " + " | ".join(cell(r.get(c)) for c in columns) + " |" for r in rows]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif suffix in (".csv", ".tsv", ""):
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore", delimiter="\t" if suffix == ".tsv" else ",")
            writer.writeheader()
            for r in rows:
                writer.writerow({c: "" if r.get(c) is None else r.get(c) for c in columns})
    else:
        raise ValueError(f"Unsupported list format '{suffix}'. Use .csv, .md or .json")
    return path


# -- reading ---------------------------------------------------------------


def _header_map(header: List[str]) -> Dict[str, int]:
    """canonical column -> index, for the first column matching each alias set."""
    found: Dict[str, int] = {}
    for i, raw in enumerate(header):
        key = raw.strip().lower().replace("‌", " ")
        for canon, names in _ALIASES.items():
            if key in names and canon not in found:
                found[canon] = i
    return found


def _is_header(row: List[str]) -> bool:
    """A header names columns; a data row (even one holding the word 'user') has numbers in it."""
    if not _header_map(row):
        return False
    return not any(re.fullmatch(r"[+\-\d\s().]*\d[+\-\d\s().]*", c.strip().translate(_DIGITS)) for c in row)


def _split_md_row(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def _md_table(text: str) -> Optional[List[List[str]]]:
    rows: List[List[str]] = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 2 and lines[0].lstrip().startswith("|") and re.fullmatch(r"[\s|:\-]+", lines[1]):
        rows.append(_split_md_row(lines[0]))
        rows += [_split_md_row(ln) for ln in lines[2:] if ln.lstrip().startswith("|")]
        return rows
    return None


def _from_table(rows: List[List[str]], column: Optional[str]) -> List[Recipient]:
    header = rows[0]
    mapping = _header_map(header)
    if column:
        idx = next((i for i, h in enumerate(header) if h.strip().lower() == column.strip().lower()), None)
        if idx is None:
            raise ValueError(f"Column '{column}' not found. Columns: {', '.join(header)}")
        mapping = {"ref": idx, **{k: v for k, v in mapping.items() if k == "name"}}
    elif not any(k in mapping for k in _REF_ORDER):
        return _from_lines(["\n".join(",".join(r) for r in rows)], None, whole=rows)
    out: List[Recipient] = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        fields = {header[i].strip(): (row[i].strip() if i < len(row) else "") for i in range(len(header))}
        get = lambda k: row[mapping[k]].strip() if k in mapping and mapping[k] < len(row) else ""
        name = get("name")
        if column:
            ref = get("ref")
            kind = classify(ref)
        else:
            kind, ref = next(((k, get(k)) for k in _REF_ORDER if get(k)), ("", ""))
            if kind == "username":
                ref = _clean_username(ref)
            elif kind == "id" and not re.fullmatch(r"-?\d+", ref.translate(_DIGITS)):
                kind = classify(ref)
        if not ref:
            continue
        if kind in ("phone", "id", "name") and classify(ref) == "username" and ref.lstrip().startswith(("@", "t.me", "http")):
            kind, ref = "username", _clean_username(ref)  # a handle typed into a phone/name column
        if kind == "id":
            ref = ref.translate(_DIGITS)
        fields.setdefault("name", name)
        out.append(Recipient(ref=ref, kind=kind, name=name, fields=fields))
    return out


def _from_lines(lines: List[str], column: Optional[str], whole: Optional[List[List[str]]] = None) -> List[Recipient]:
    out: List[Recipient] = []
    items: List[str] = []
    if whole is not None:  # a header-less table: every cell of the first column is a reference
        items = [r[0] for r in whole if r and r[0].strip()]
    else:
        for line in lines[0].splitlines():
            line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()
            if line and not line.startswith("#"):
                items.append(line.split(",")[0].strip() if "," in line else line)
    for item in items:
        kind = classify(item)
        ref = _clean_username(item) if kind == "username" else item.translate(_DIGITS) if kind == "id" else item
        out.append(Recipient(ref=ref, kind=kind, name=item if kind == "name" else "", fields={}))
    return out


def parse_recipients(text: str, suffix: str = ".csv", column: Optional[str] = None) -> List[Recipient]:
    text = text.lstrip("﻿")
    table = _md_table(text) if suffix.lower() in (".md", ".markdown", ".txt") else None
    if table is None and suffix.lower() in (".csv", ".tsv"):
        delimiter = "\t" if suffix.lower() == ".tsv" else (csv.Sniffer().sniff(text.splitlines()[0], ",;\t").delimiter if text.strip() and any(d in text.splitlines()[0] for d in ",;\t") else ",")
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
        if rows and (column or _is_header(rows[0])):
            table = rows
        elif rows:
            return _from_lines(["\n".join(r[0] for r in rows)], None)
    if table is not None:
        return _from_table(table, column)
    return _from_lines([text], column)


def read_recipients(path: Path, column: Optional[str] = None) -> List[Recipient]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Recipient list not found: {path}")
    recipients = parse_recipients(path.read_text(encoding="utf-8-sig"), path.suffix or ".txt", column)
    if not recipients:
        raise ValueError(f"No recipients found in {path}")
    return recipients
