"""Launcher used by PyInstaller and for `python run.py`."""
import sys

from macrorecorder.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
