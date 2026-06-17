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
