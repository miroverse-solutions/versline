import os
import hashlib
from pathlib import Path
from datetime import timedelta
from difflib import SequenceMatcher
from typing import Optional

def format_duration(seconds: float) -> str:
    """Format seconds to HH:MM:SS"""
    if seconds is None or seconds < 0:
        return "00:00:00"
    
    td = timedelta(seconds=int(seconds))
    hours, remainder = divmod(td.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to be safe for OS"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    filename = ' '.join(filename.split())
    
    max_length = 255
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    
    return filename

def find_best_text_overlap_point(text1, text2, expected_overlap_chars=800):
    """Find the best point to join two texts by finding overlapping section."""
    len1, len2 = len(text1), len(text2)
    
    search_area1 = text1[max(0, len1 - expected_overlap_chars):]
    search_area2 = text2[:min(len2, expected_overlap_chars)]
    
    matcher = SequenceMatcher(None, search_area1, search_area2, autojunk=False)
    match = matcher.find_longest_match(0, len(search_area1), 0, len(search_area2))
    
    if match.size > 25:
        start_in_text1 = max(0, len1 - expected_overlap_chars) + match.a
        end_in_text2 = match.b + match.size
        # Keep overlap from first text, skip from second to avoid duplication
        return text1[:start_in_text1 + match.size], text2[end_in_text2:]
    
    return text1, "\n" + text2


def align_cheap_to_good_text(good_text: str, cheap_chunks: list[tuple[float, float, str]]) -> list[dict]:
    """Align good transcript with timestamped cheap chunks.

    Strategy: proportional first, then fuzzy refinement within a local window.
    This handles cases where cheap model output differs significantly from good text."""
    segments = []
    total_dur = cheap_chunks[-1][1] if cheap_chunks else 1
    good_len = len(good_text)
    chars_per_sec = good_len / total_dur if total_dur > 0 else 10

    for idx, (start_sec, end_sec, cheap_text) in enumerate(cheap_chunks):
        cheap_clean = cheap_text.strip()
        if not cheap_clean:
            continue

        # 1. Proportional estimate
        prop_center = int((start_sec / total_dur) * good_len)
        # Expected segment length in chars (~2000-4000 for 3min)
        expected_len = int(chars_per_sec * (end_sec - start_sec))
        window_radius = max(expected_len * 3, 500)

        # 2. Search window around proportional position
        win_start = max(0, prop_center - window_radius)
        win_end = min(good_len, prop_center + window_radius)
        search_region = good_text[win_start:win_end]
        if not search_region:
            continue

        # 3. Fuzzy match within window
        search_key = cheap_clean[:200]
        matcher = SequenceMatcher(None, search_key, search_region, autojunk=False)
        match = matcher.find_longest_match(0, len(search_key), 0, len(search_region))

        if match.size > 15:
            best_pos = win_start + match.b
        elif match.size > 6:
            # Weak match — use it anyway if it's near proportional
            best_pos = win_start + match.b
        else:
            # No match — fall back to proportional
            best_pos = prop_center

        # 4. Determine end: look for next chunk's match or use proportional
        next_pos = good_len
        for ns, ne, nt in cheap_chunks:
            if ns <= start_sec or not nt.strip():
                continue
            # Search a small window after best_pos
            look_ahead = good_text[best_pos + 20:min(good_len, best_pos + expected_len * 3)]
            if not look_ahead:
                break
            matcher2 = SequenceMatcher(None, nt.strip()[:100], look_ahead, autojunk=False)
            match2 = matcher2.find_longest_match(0, min(100, len(nt.strip())), 0, len(look_ahead))
            if match2.size > 10:
                next_pos = best_pos + 20 + match2.b
                break

        if next_pos == good_len:
            # No next-chunk match found — use proportional end
            prop_next = int(((end_sec) / total_dur) * good_len)
            next_pos = max(best_pos + 100, prop_next)

        # 5. Extract segment
        if next_pos <= best_pos:
            next_pos = min(good_len, best_pos + expected_len)
        segment_text = good_text[best_pos:next_pos].strip()
        if not segment_text and best_pos < good_len:
            segment_text = good_text[best_pos:min(good_len, best_pos + expected_len)].strip()

        segments.append({
            'start': round(start_sec, 1),
            'end': round(end_sec, 1),
            'text': segment_text or cheap_clean[:150],
        })

    return segments


_PERSIAN_CHAR_MAP = str.maketrans({
    "ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا", "آ": "ا",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})
_PERSIAN_STRIP = dict.fromkeys(map(ord, "‌‍‏‎ـًٌٍَُِّْ"), None)


def _norm_token(token: str) -> str:
    """Lowercase, unify Arabic/Persian letter variants and drop ZWNJ, diacritics and punctuation."""
    token = token.translate(_PERSIAN_CHAR_MAP).translate(_PERSIAN_STRIP).lower()
    return "".join(ch for ch in token if ch.isalnum())


def _align_token_gap(a: list[str], b: list[str], min_ratio: float = 0.5) -> list[tuple[int, int]]:
    """Needleman-Wunsch over a small gap using fuzzy character similarity. Returns (i, j) pairs."""
    n, m = len(a), len(b)
    if not n or not m or n * m > 4_000_000:
        return []
    gap = -0.5
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]  # 1=diag, 2=up (skip a), 3=left (skip b)
    for i in range(1, n + 1):
        score[i][0], back[i][0] = i * gap, 2
    for j in range(1, m + 1):
        score[0][j], back[0][j] = j * gap, 3
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best, move = score[i - 1][j] + gap, 2
            if score[i][j - 1] + gap > best:
                best, move = score[i][j - 1] + gap, 3
            ratio = 1.0 if a[i - 1] == b[j - 1] else SequenceMatcher(None, a[i - 1], b[j - 1]).ratio()
            if ratio >= min_ratio and score[i - 1][j - 1] + ratio * 2 - 1 >= best:
                best, move = score[i - 1][j - 1] + ratio * 2 - 1, 1
            score[i][j], back[i][j] = best, move
    pairs, i, j = [], n, m
    while i > 0 or j > 0:
        move = back[i][j]
        if move == 1:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif move == 2:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def align_words_to_good_text(
    good_text: str,
    words: list[dict],
    total_duration: Optional[float] = None,
    min_len: float = 2.5,
    max_len: float = 14.0,
) -> list[dict]:
    """Split the good transcript into timed segments using word-level timestamps from an STT API.

    The STT words (start/end/word) are matched to the good text's words (exact anchors first,
    fuzzy DP inside the gaps), so the STT's own spelling/style never leaks into the output.
    Unmatched words get interpolated times. The good text is cut only at word boundaries and
    every character of it ends up in exactly one segment."""
    import re

    stt = []
    for w in words or []:
        try:
            start, end = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        norm = _norm_token(str(w.get("word", "")))
        if norm:
            stt.append((norm, start, end))
    spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", good_text)]
    if not stt or not spans:
        return []

    good_norm = [_norm_token(good_text[s:e]) for s, e in spans]
    stt_norm = [t[0] for t in stt]

    # Match good-word index -> stt-word index
    match: dict[int, int] = {}
    good_idx = [i for i, t in enumerate(good_norm) if t]
    good_tokens = [good_norm[i] for i in good_idx]
    blocks = [b for b in SequenceMatcher(None, good_tokens, stt_norm, autojunk=False).get_matching_blocks() if b.size >= 3]
    prev_a = prev_b = 0
    for block in blocks + [None]:
        a_end, b_end = (block.a, block.b) if block else (len(good_tokens), len(stt_norm))
        for ia, jb in _align_token_gap(good_tokens[prev_a:a_end], stt_norm[prev_b:b_end]):
            match[good_idx[prev_a + ia]] = prev_b + jb
        if block:
            for k in range(block.size):
                match[good_idx[block.a + k]] = block.b + k
            prev_a, prev_b = block.a + block.size, block.b + block.size

    # Per-word times: matched -> STT time, unmatched -> interpolate (weighted by length) between neighbours
    n = len(spans)
    audio_end = total_duration if total_duration else stt[-1][2]
    starts = [0.0] * n
    ends = [0.0] * n
    known = [i for i in range(n) if i in match]
    for i in known:
        starts[i], ends[i] = stt[match[i]][1], stt[match[i]][2]
    anchors = [(-1, 0.0)] + [(i, None) for i in known] + [(n, audio_end)]
    for (left, _), (right, _) in zip(anchors, anchors[1:]):
        gap_ids = list(range(left + 1, right))
        if not gap_ids:
            continue
        t0 = ends[left] if left >= 0 else 0.0
        t1 = starts[right] if right < n else audio_end
        t1 = max(t1, t0)
        weights = [max(1, len(good_text[spans[i][0]:spans[i][1]])) for i in gap_ids]
        total_w = sum(weights)
        cursor = t0
        for i, w in zip(gap_ids, weights):
            starts[i] = cursor
            cursor += (t1 - t0) * w / total_w
            ends[i] = cursor

    # Cut into segments at sentence ends / paragraph breaks, never exceeding max_len
    sentence_end = (".", "!", "?", "؟", "…", ":")
    soft_end = (",", "،", "؛", ";")
    segments = []
    seg_first = 0
    for i in range(n):
        word = good_text[spans[i][0]:spans[i][1]]
        dur = ends[i] - starts[seg_first]
        last = i == n - 1
        para_break = not last and "\n" in good_text[spans[i][1]:spans[i + 1][0]]
        cut = last or para_break and dur >= min_len
        if not cut and dur >= min_len:
            stripped = word.rstrip("*_»\")]")
            cut = stripped.endswith(sentence_end) or (dur >= max_len * 0.6 and stripped.endswith(soft_end))
        if not cut and dur >= max_len:
            cut = True
        if cut:
            seg_start = spans[seg_first][0] if segments else 0
            seg_end = len(good_text) if last else spans[i][1]
            text = good_text[seg_start:seg_end].strip()
            if text:
                segments.append({
                    "start": round(starts[seg_first], 1),
                    "end": round(max(ends[i], starts[seg_first]), 1),
                    "text": text,
                })
            seg_first = i + 1
    return segments
