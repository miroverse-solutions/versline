"""PyInstaller entry point for the self-contained Versline build."""
import multiprocessing

from versline.cli import app

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app()
