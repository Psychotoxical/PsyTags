"""Checks that a pull request adds an entry under [Unreleased] in CHANGELOG.md.

    python packaging/check_changelog.py BASE_CHANGELOG HEAD_CHANGELOG

Every pull request needs one: the entries under [Unreleased] become the section of the next
version. Exits with 1 if HEAD has no entry under [Unreleased] that BASE does not have.
"""
import re
import sys

HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\].*$", re.MULTILINE)


def unreleased_entries(text: str) -> set[str]:
    """The non-empty lines under [Unreleased] that are not headings."""
    matches = list(HEADING.finditer(text))
    for i, m in enumerate(matches):
        if m.group("version") == "Unreleased":
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return {line.strip() for line in text[m.end():end].splitlines()
                    if line.strip() and not line.startswith("#")}
    return set()


def new_entries(base: str, head: str) -> set[str]:
    return unreleased_entries(head) - unreleased_entries(base)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        base = f.read()
    with open(argv[2], encoding="utf-8") as f:
        head = f.read()
    added = new_entries(base, head)
    if not added:
        print("::error file=CHANGELOG.md::Add an entry under '## [Unreleased]' in CHANGELOG.md "
              "describing what this pull request changes for users.")
        return 1
    for line in sorted(added):
        print(f"new: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
