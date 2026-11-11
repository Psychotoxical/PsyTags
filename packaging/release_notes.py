"""Prints the release text of a version: its CHANGELOG.md section plus the download table.

    python packaging/release_notes.py [VERSION]

Without VERSION it takes the version of the package. Exits with 1 if the section is missing or empty.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\]", re.MULTILINE)

DOWNLOADS = """## Download

| System | File |
|---|---|
| Windows 10 and 11 | `PsyTags-Setup-{version}.exe` |
| Debian, Ubuntu, Mint | `psytags_{version}_amd64.deb` |
| Fedora, openSUSE | `psytags-{version}-1.x86_64.rpm` |
| Other Linux | `PsyTags-x86_64.AppImage`: `chmod +x`, then start it |
"""


def section(text: str, version: str) -> str:
    """The body of the section for version, without its heading; empty if there is none."""
    matches = list(HEADING.finditer(text))
    for i, m in enumerate(matches):
        if m.group("version") == version:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end():end].partition("\n")[2].strip()   # drops the rest of the heading line
    return ""


def notes(text: str, version: str) -> str:
    body = section(text, version)
    if not body:
        raise ValueError(f"CHANGELOG.md has no section for {version}")
    body = re.sub(r"^### ", "## ", body, flags=re.MULTILINE)
    return f"{body}\n\n{DOWNLOADS.format(version=version)}"


def package_version() -> str:
    init = (ROOT / "psytags" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', init).group(1)


def main(argv: list[str]) -> int:
    version = argv[1] if len(argv) > 1 else package_version()
    try:
        print(notes((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
