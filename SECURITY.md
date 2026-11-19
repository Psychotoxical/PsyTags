# Security

Please report security problems privately via **Security → Report a vulnerability** on GitHub, not in a public issue. You will get an answer as soon as possible.

Only the latest release gets fixes.

## Signed downloads

- **Windows:** the installer, its uninstaller and `PsyTags.exe` are signed with a Certum open source code signing certificate. Check it under **Properties → Digital Signatures** of the file, or with `Get-AuthenticodeSignature PsyTags-Setup-<version>.exe` in PowerShell; the status must be `Valid`.
- **macOS:** both disk images and the app are signed with an Apple Developer ID and notarized by Apple. Check it with `spctl --assess --type open --context context:primary-signature --verbose=2 PsyTags-<version>-macOS-<arch>.dmg`.
- **Linux:** the AppImage, deb and rpm are not signed. The Releases page lists the SHA256 checksum of every file; compare it with `sha256sum`.

Only download PsyTags from the [Releases](https://github.com/Psysonic/PsyTags/releases) page.
