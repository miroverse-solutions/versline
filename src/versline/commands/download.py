import typer
import httpx
from pathlib import Path
from loguru import logger
from versline.utils import sanitize_filename

app = typer.Typer(help="Download files from URLs.")

@app.command("url")
def download_url(
    url: str = typer.Argument(..., help="URL to download"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path/directory"),
):
    """
    Download a file from a URL.
    """
    try:
        if output and output.is_dir():
             # Try to get filename from URL
            filename = url.split("/")[-1]
            # Simple check for params in url
            if "?" in filename:
                filename = filename.split("?")[0]
            output = output / (filename or "downloaded_file")

        logger.info(f"Downloading {url}...")
        
        with httpx.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            
            # If output is still None, try to deduce from headers or url
            if not output:
                 # TODO: improved filename extraction from Content-Disposition
                filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
                output = Path(filename)

            total = int(response.headers.get("Content-Length", 0))
            
            with open(output, "wb") as f:
                downloaded = 0
                with typer.progressbar(length=total, label="Downloading") as progress:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress.update(len(chunk))
                        
        logger.success(f"Downloaded to {output}")
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
