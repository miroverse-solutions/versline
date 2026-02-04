"""Caching utilities for Versqude."""

import hashlib
import json
from pathlib import Path
from typing import Optional, List, Dict, Any


def get_cache_key(content: str, prompt: str, batch_info: str, model: str) -> str:
    """Generate a unique cache key based on content and settings."""
    key_data = f"{content}|{prompt}|{batch_info}|{model}"
    return hashlib.md5(key_data.encode()).hexdigest()


def get_cache_path(cache_dir: Path, cache_key: str) -> Path:
    """Get the cache file path for a given cache key."""
    return cache_dir / f"cache_{cache_key}.json"


def load_from_cache(cache_dir: Optional[Path], cache_key: str) -> tuple[list[dict], str] | None:
    """Load questions from cache if available.
    
    Returns (questions, raw_response) or None.
    """
    if not cache_dir:
        return None
    
    cache_path = get_cache_path(cache_dir, cache_key)
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("questions", []), data.get("raw_response", "")
        except Exception:
            return None
    return None


def save_to_cache(
    cache_dir: Path,
    cache_key: str,
    questions: list[dict],
    raw_response: str = ""
):
    """Save questions and raw response to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = get_cache_path(cache_dir, cache_key)
    
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "questions": questions,
                "raw_response": raw_response,
                "cache_key": cache_key,
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save cache: {e}")


def load_all_from_cache(cache_dir: Path) -> list[dict]:
    """Load all questions from cache directory."""
    if not cache_dir or not cache_dir.exists():
        return []
    
    all_questions = []
    cache_files = sorted(cache_dir.glob("cache_*.json"))
    
    if not cache_files:
        print(f"No cache files found in: {cache_dir}")
        return []
    
    print(f"📂 Found {len(cache_files)} cache file(s)")
    
    for cache_file in cache_files:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                questions = data.get("questions", []), data.get("raw_response", "")
                all_questions.extend(questions)
                print(f"  ✓ Loaded {len(questions)} questions from {cache_file.name}")
        except Exception as e:
            print(f"  ✗ Failed to load {cache_file.name}: {e}")
    
    return all_questions

class CacheManager:
    """Manages caching of generated questions at the file level."""
    
    def __init__(self, output_dir: Path, disabled: bool = False):
        self.output_dir = output_dir
        self.disabled = disabled
        self.cache_dir = output_dir / ".cache"
        if not disabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
    def get(self, file_path: Path, question_type: str, language: str) -> Optional[List[Dict]]:
        if self.disabled:
             return None
        
        cache_file = self._get_file_cache_path(file_path, question_type, language)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def set(self, file_path: Path, question_type: str, language: str, data: List[Dict]):
        if self.disabled:
            return
            
        cache_file = self._get_file_cache_path(file_path, question_type, language)
        try:
             with open(cache_file, "w", encoding="utf-8") as f:
                 json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
             pass

    def _get_file_cache_path(self, file_path: Path, question_type: str, language: str) -> Path:
        # Create a unique name for file cache
        # e.g. filename_hash_qtype_lang.json
        file_hash = hashlib.md5(str(file_path.name).encode()).hexdigest()[:8]
        name = f"{file_path.stem}_{file_hash}_{question_type}_{language}.json"
        return self.cache_dir / name
