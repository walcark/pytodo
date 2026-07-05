"""Enable `python -m pytodo ...` (used to launch the detached background sync)."""

from .cli import app

if __name__ == "__main__":
    app()
