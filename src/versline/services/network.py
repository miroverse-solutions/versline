import httpx
from pathlib import Path
from loguru import logger
import os
from urllib.parse import urlparse, unquote

def download_file(url: str, destination_dir: Path) -> Path:
    """
    Download a file from a URL to the destination directory.
    Returns the path to the downloaded file.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    
    # Try to extract filename from URL path first
    parsed_url = urlparse(url)
    path_filename = os.path.basename(unquote(parsed_url.path))
    
    if not path_filename or "." not in path_filename:
        path_filename = "downloaded_file"

    temp_path = destination_dir / path_filename
    
    logger.info(f"Downloading from {url}...")
    
    try:
        with httpx.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            
            # Check for Content-Disposition header filename if URL didn't have one
            # (Simplified check, robust parsing requires a library like python-multipart or regex)
            
            total = int(response.headers.get("Content-Length", 0))
            
            with open(temp_path, "wb") as f:
                downloaded = 0
                for chunk in response.iter_bytes():
                    f.write(chunk)
                    downloaded += len(chunk)
                    # We could yield progress here if needed, but for now simple log/blocking is fine for this utility
                    
        logger.success(f"Downloaded: {temp_path}")
        return temp_path
        
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        raise
