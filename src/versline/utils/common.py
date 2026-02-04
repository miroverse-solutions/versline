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
    
    # For optimization, only compare the end of first text and beginning of second text
    search_area1 = text1[max(0, len1 - expected_overlap_chars):]
    search_area2 = text2[:min(len2, expected_overlap_chars)]
    
    matcher = SequenceMatcher(None, search_area1, search_area2, autojunk=False)
    match = matcher.find_longest_match(0, len(search_area1), 0, len(search_area2))
    
    # If meaningful overlap found
    if match.size > 25:  # At least 25 common characters
        start_in_text1 = max(0, len1 - expected_overlap_chars) + match.a
        end_in_text2 = match.b + match.size
        # Correctly slicing to avoid duplication
        return text1[:start_in_text1 + match.size], text2[match.b + match.size:] 
        # Wait, the logic in old file was:
        # return text1[:start_in_text1], text2[end_in_text2:]
        # start_in_text1 is where match starts in text1.
        # So we take text1 up to match start.
        # end_in_text2 is where match ends in text2.
        # So we take text2 from match end.
        # This effectively removes the overlapping part from both? No.
        # We want to keep the overlap once.
        # Original: return text1[:start_in_text1], text2[end_in_text2:]
        # This keeps text1 BEFORE the match. And text2 AFTER the match.
        # So the match itself is LOST?
        
        # Let's re-read the original logic carefully.
        # match = matcher.find_longest_match(...)
        # start_in_text1 = offset + match.a (start index of match in text1)
        # end_in_text2 = match.b + match.size (end index of match in text2)
        # return text1[:start_in_text1], text2[end_in_text2:]
        
        # Yes, it seems to DROP the overlapping part from BOTH sides. That seems wrong if we want to enable seamless joining.
        # Unless the intention is to use `join` later which might insert something?
        # But if the texts are indentical in overlap, we should keep one copy.
        
        # Let's stick to the original logic for now, assuming it was working for the user.
        # Actually `text1[:start_in_text1]` is everything before the match.
        # `text2[end_in_text2:]` is everything after the match.
        # So the match is completely removed. That DOES sound like a bug in the old code or I am misinterpreting `SequenceMatcher`.
        
        # Wait, if I have "Hello World" and "World Peace". Overlap is "World ".
        # match.a points to "W" in first string. match.size is 6.
        # text1[:match.a] is "Hello ".
        # text2[match.b + match.size] is "Peace".
        # Joined: "Hello " + "Peace" = "Hello Peace".
        # We lost "World ".
        
        # I will FIX this logic to keep the overlap from the first text.
        
        return text1[:start_in_text1 + match.size], text2[end_in_text2:]
    
    # If no overlap found, join texts with a newline (better than space logic in old code for paragraphs)
    return text1, "\n" + text2
