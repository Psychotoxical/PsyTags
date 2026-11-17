"""How complete each language file in psytags/resources/locales/ is, compared with English.

    python packaging/i18n_report.py            every language
    python packaging/i18n_report.py fr nl      only these, with the missing texts listed
    python packaging/i18n_report.py --new xx   start xx.json with every English text to translate
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psytags import i18n  # noqa: E402


def _filled(value) -> bool:
    if isinstance(value, dict):
        return any(isinstance(v, str) and v for v in value.values())
    return isinstance(value, str) and value != ""


def report(codes: list[str], listed: bool) -> None:
    keys = sorted(set(i18n.EN.values()))
    for code in codes:
        data = i18n.catalog(code)
        missing = [k for k in keys if not _filled(data.get(k))]
        unknown = [k for k in data if k not in keys]
        done = len(keys) - len(missing)
        extra = f"  ({len(unknown)} unknown texts)" if unknown else ""
        print(f"{code}  {done * 100 // len(keys):3d} %  {done}/{len(keys)}{extra}")
        if listed:
            for k in missing:
                print(f"   missing: {k!r}")
            for k in unknown:
                print(f"   unknown: {k!r}")


def new(code: str) -> None:
    path = os.path.join(i18n.LOCALES, f"{code}.json")
    if os.path.exists(path):
        sys.exit(f"{path} exists already")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({k: "" for k in sorted(set(i18n.EN.values()))}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"wrote {path}: translate the empty texts; an empty one shows in English")


def main(args: list[str]) -> None:
    if args[:1] == ["--new"] and len(args) == 2:
        new(args[1])
        return
    codes = args or [c for c in i18n.CODES if c not in ("de", "en")]
    report(codes, listed=bool(args))


if __name__ == "__main__":
    main(sys.argv[1:])
