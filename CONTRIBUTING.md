# Contributing to PsyTags

Thanks for helping. Bug reports, ideas, translations and code are all welcome.

## Issues

Open an issue with one of the templates. For a bug, name the PsyTags version, the system and the package (installer, AppImage, deb, rpm, DMG), and the steps that lead to it. Security problems go through [SECURITY.md](SECURITY.md), not a public issue.

## Translations

Every language is one JSON file; [Translating PsyTags](README.md#translating-psytags) in the README explains the format, the plural forms and how to start a new language. A pull request that only touches a language file is fine.

## Code

1. Set up the project as in [Running from source](README.md#running-from-source), with `pip install -e .`.
2. Make the change on a branch and open a pull request against `main`. Keep one topic per pull request.
3. Before you push, run what CI runs:

   ```
   QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
   ruff check .
   ```

### House rules

- **Changelog:** every pull request adds at least one line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), in the section that fits (`Added`, `Changed`, `Fixed`). Write it for users: what they notice, not how it is built. CI fails without it.
- **Texts in the interface:** the code holds German texts. A new text needs its English version in `EN` in `psytags/i18n.py`; the language files take the English text as key. Missing translations show in English, so you do not have to fill in every language.
- **Help:** if a function changes, update its page in `psytags/resources/help/de/` and `en/`.
- **Tests:** a fix comes with a test that fails without it. Test data uses neutral placeholders ("Band", "Album", files in the temp folder), never real music or personal paths.
- **Real files:** PsyTags writes tags and renames files. Try changes on copies, never on a collection you care about.

## How a pull request goes in

CI runs the changelog check, Ruff, ShellCheck, actionlint and, when code changes, the tests on Linux. The check `ci-ok` sums it up and must be green. Only maintainers merge: a maintainer reviews the pull request and squashes it into `main`. Please do not merge your own pull request, even if you have write access.

Releases are built by the maintainers: the release workflow runs the tests on Windows and macOS too, builds and signs all packages and creates a draft. Contributors do not need to change the version number.
