"""Tag source files in data/sources: .src scripts and .settings schemas."""
from __future__ import annotations

import glob
import os
import re

from . import config


def sources_dir() -> str:
    return os.path.join(config.data_dir(), "sources")


def _natural(s: str):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", s) if t]


def list_sources() -> list[tuple[str, str]]:
    """(menu path with '#' submenus and '&' mnemonics, file path), naturally sorted."""
    out = [(os.path.splitext(os.path.basename(p))[0], p)
           for p in glob.glob(os.path.join(sources_dir(), "*.src"))]
    out.sort(key=lambda x: _natural(x[0].replace("&", "")))
    return out


def list_settings() -> list[tuple[str, str]]:
    out = [(os.path.splitext(os.path.basename(p))[0], p)
           for p in glob.glob(os.path.join(sources_dir(), "*.settings"))]
    out.sort(key=lambda x: _natural(x[0].replace("&", "")))
    return out
