"""Paths longer than Windows' MAX_PATH.

Explorer and players open such files, but Python's file functions fail with "path not found"
unless long paths are enabled for the whole system. The ``\\\\?\\`` form works everywhere.
"""
import os
import sys

LIMIT = 247                     # MAX_PATH minus room for a file name in a folder (248)


def io(path: str) -> str:
    """``path`` in a form the file functions accept; unchanged where it already fits."""
    if sys.platform != "win32" or len(path) <= LIMIT or path.startswith("\\\\?\\"):
        return path
    full = os.path.abspath(path)
    if full.startswith("\\\\"):                     # \\server\share\...
        return "\\\\?\\UNC\\" + full[2:]
    return "\\\\?\\" + full
