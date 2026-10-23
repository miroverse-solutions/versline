import subprocess
import os
from loguru import logger
import shutil
from versline.config import settings


def _bundled_binaries():
    """Download-on-first-use static ffmpeg/ffprobe (static-ffmpeg package). Returns (ffmpeg, ffprobe) or (None, None)."""
    try:
        from static_ffmpeg.run import get_or_fetch_platform_executables_else_raise

        return get_or_fetch_platform_executables_else_raise()
    except Exception as e:
        logger.debug(f"Bundled ffmpeg unavailable: {e}")
        return None, None


def resolve_ffmpeg() -> str:
    """Explicit setting, then PATH, then the bundled static build."""
    return settings.ffmpeg.ffmpeg_path or shutil.which("ffmpeg") or _bundled_binaries()[0] or "ffmpeg"


def resolve_ffprobe() -> str:
    return settings.ffmpeg.ffprobe_path or shutil.which("ffprobe") or _bundled_binaries()[1] or "ffprobe"

def get_audio_duration(file_path: str) -> float:
    """Get audio file duration using ffprobe."""
    ffprobe_path = resolve_ffprobe()
    
    try:
        result = subprocess.run(
            [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', 
             '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return float(result.stdout.strip())
    except FileNotFoundError:
        logger.error(f"❌ FFprobe executable not found at '{ffprobe_path}'. Please check your configuration.")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error reading file duration: {e}. stderr: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error reading file duration: {e}")
        return None

def split_audio_with_ffmpeg(file_path: str, chunk_length_sec: int, chunk_overlap_sec: int, temp_dir: str) -> list[str]:
    """Split audio file into specified chunks with overlap using ffmpeg.
    
    Chunks are written in the same container format as the source file
    to avoid codec/container mismatches (e.g., AAC-in-M4A copied into .mp3).
    """
    ffmpeg_path = resolve_ffmpeg()
    
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    logger.info(f"Processing and splitting file '{os.path.basename(file_path)}'...")

    duration = get_audio_duration(file_path)
    if duration is None:
        return []

    logger.info(f"Total file duration: {duration/60:.2f} minutes")
    
    # Match chunk container to source file so -c copy always works
    src_ext = os.path.splitext(file_path)[1]  # e.g. ".m4a", ".mp3", ".wav"
    if src_ext.lower() not in (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".flac", ".wma", ".m4b"):
        src_ext = ".mp3"  # fallback for unknown formats
    
    chunk_paths = []
    step_size_sec = chunk_length_sec - chunk_overlap_sec
    current_time = 0
    chunk_index = 0
    
    while current_time < duration:
        chunk_name = f"chunk_{chunk_index:03d}{src_ext}"
        chunk_path = os.path.join(temp_dir, chunk_name)
        
        # Calculate this chunk's duration
        chunk_duration = min(chunk_length_sec, duration - current_time)

        # Skip if chunk is too short (less than 10 seconds) unless it's the only/last chunk and still meaningful? 
        # Old code break < 10.
        if chunk_duration < 10:
            break
        
        try:
            # Use ffmpeg to cut the file
            cmd = [
                ffmpeg_path, '-i', file_path, '-ss', str(current_time), 
                '-t', str(chunk_duration), '-c', 'copy', '-y', chunk_path
            ]
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            chunk_paths.append(chunk_path)
            # logger.debug(f"Chunk created: {chunk_path}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Error creating chunk {chunk_index}: {e}")
            break
        except FileNotFoundError:
             logger.error(f"❌ FFmpeg executable not found at '{ffmpeg_path}'.")
             return []
        
        current_time += step_size_sec
        chunk_index += 1
        
    return chunk_paths
