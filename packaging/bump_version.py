"""Raises the version for a release candidate and brings main up to date after a release.

    python packaging/bump_version.py next [PUBLISHED ...]
    python packaging/bump_version.py sync VERSION RELEASED_CHANGELOG

next: PUBLISHED are the versions that are already released. If the version in
psytags/__init__.py is one of them, the next free patch version goes into psytags/__init__.py
and pyproject.toml, and the entries under [Unreleased] in CHANGELOG.md become its section.
Prints the version. Used by the main → next workflow on the next branch only.

sync: after VERSION was released, main gets that version and the section from the released
CHANGELOG.md; the entries that went into the release leave [Unreleased].
"""
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\].*$", re.MULTILINE)
INIT = ROOT / "psytags" / "__init__.py"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def bump_patch(version: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def next_version(current: str, published: set[str]) -> str:
    version = current
    while version in published:
        version = bump_patch(version)
    return version


def set_init_version(text: str, version: str) -> str:
    return re.sub(r'^__version__ = "[^"]*"$', f'__version__ = "{version}"', text, count=1, flags=re.M)


def set_pyproject_version(text: str, version: str) -> str:
    return re.sub(r'^version = "[^"]*"$', f'version = "{version}"', text, count=1, flags=re.M)


def _sections(text: str) -> list[tuple[str, int, int, int]]:
    """(version, start of heading, start of body, end of body) for every '## [...]' heading."""
    matches = list(HEADING.finditer(text))
    return [(m.group("version"), m.start(), m.end(),
             matches[i + 1].start() if i + 1 < len(matches) else len(text))
            for i, m in enumerate(matches)]


def _find(text: str, version: str) -> tuple[str, int, int, int] | None:
    return next((s for s in _sections(text) if s[0] == version), None)


def release_unreleased(text: str, version: str, date: str) -> str:
    """Turns the entries under [Unreleased] into the section of version; unchanged if it has one."""
    if _find(text, version):
        return text
    unreleased = _find(text, "Unreleased")
    if not unreleased:
        raise ValueError("CHANGELOG.md has no '## [Unreleased]' section")
    _, start, body_start, end = unreleased
    body = text[body_start:end].strip()
    if not body:
        raise ValueError("CHANGELOG.md has nothing under [Unreleased] to release")
    block = f"## [Unreleased]\n\n## [{version}] - {date}\n\n{body}\n\n"
    return text[:start] + block + text[end:]


def _drop_empty_headings(lines: list[str]) -> list[str]:
    """Removes '###' headings that have no entry left before the next heading."""
    kept: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("### "):
            rest = lines[i + 1:]
            nxt = next((j for j, r in enumerate(rest) if r.startswith("#")), len(rest))
            if not any(r.strip() for r in rest[:nxt]):
                continue
        kept.append(line)
    return kept


def sync_released(text: str, released: str, version: str) -> str:
    """Adds the section of version from released and takes its entries out of [Unreleased]."""
    if _find(text, version):
        return text
    found = _find(released, version)
    if not found:
        raise ValueError(f"the released CHANGELOG.md has no section for {version}")
    _, r_start, r_body_start, r_end = found
    heading = released[r_start:r_body_start]
    body = released[r_body_start:r_end].strip()
    entries = {line for line in body.splitlines() if line.strip() and not line.startswith("#")}

    unreleased = _find(text, "Unreleased")
    if not unreleased:
        raise ValueError("CHANGELOG.md has no '## [Unreleased]' section")
    _, start, body_start, end = unreleased
    left = [line for line in text[body_start:end].strip().splitlines() if line not in entries]
    left_text = re.sub(r"\n{3,}", "\n\n", "\n".join(_drop_empty_headings(left))).strip()
    block = "## [Unreleased]\n\n" + (f"{left_text}\n\n" if left_text else "") + f"{heading}\n\n{body}\n\n"
    return text[:start] + block + text[end:]


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: pathlib.Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def current_version() -> str:
    return re.search(r'^__version__ = "([^"]+)"$', _read(INIT), re.M).group(1)


def set_version(version: str) -> None:
    _write(INIT, set_init_version(_read(INIT), version))
    _write(PYPROJECT, set_pyproject_version(_read(PYPROJECT), version))


def main(argv: list[str]) -> int:
    try:
        if len(argv) >= 2 and argv[1] == "next":
            current = current_version()
            version = next_version(current, set(argv[2:]))
            if version != current:
                today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                _write(CHANGELOG, release_unreleased(_read(CHANGELOG), version, today))
                set_version(version)
            print(version)
            return 0
        if len(argv) == 4 and argv[1] == "sync":
            version = argv[2]
            released = _read(pathlib.Path(argv[3]))
            _write(CHANGELOG, sync_released(_read(CHANGELOG), released, version))
            if _key(current_version()) < _key(version):
                set_version(version)
            return 0
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
