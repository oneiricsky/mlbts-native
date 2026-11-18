# Security Policy

## Supported Versions

Security fixes are provided only for the **latest release** of Fastball (`VERSION`, currently `0.1.4`), targeting offline play on Nintendo Switch game versions **1.0.20** (primary) and **1.0.15**.

| Target | Supported |
|---|---|
| Latest Fastball release (`0.1.4`) | Yes |
| Older Fastball releases | No (update to the latest release) |
| Switch game versions `1.0.20` and `1.0.15` (offline only) | Yes |
| Other Switch game versions | No |

## Reporting a Vulnerability

Please report security vulnerabilities privately through **GitHub Private Vulnerability Reporting**:

- Go to the repository's **Security** tab and click **Report a vulnerability**.
- Do **not** open a public GitHub issue or pull request for unpatched security bugs.

> **Never attach keys or copyrighted game material to a report.**
> Do **not** include `prod.keys`, `title.keys`, `.nsp` / `.xci` / `.nca` dumps, extracted game data, or compiled `mlb.exe` binaries. Attach only sanitized reproduction steps and, if relevant, `logs/mlb.log` or `logs/setup-*.log`.

### What to Include

- Fastball version (from `VERSION`) and Switch game version (`1.0.20` or `1.0.15`)
- Affected component or file path, if known
- Clear steps to reproduce or proof of concept (without proprietary game files or keys)

### Response Expectations

This is a fan project maintained on a best-effort basis. Reports are triaged as time permits, and coordinated disclosure is preferred after a patched Fastball release is published.

## Scope

### In Scope

Security issues affecting the user's host system, keys, or build/update supply chain:

- **Setup, launcher, and auto-updater** (`installer/`, `installer/update.py`, `installer/launcher/`): release metadata/asset SHA-256 verification, path traversal or unsafe file writes during unpacking, installation, or Ryujinx save import.
- **Game dump & key handling** (`tools/romfs_dump.py`, `tools/ncastorage.py`, `tools/swcrypto.py`, `installer/`): ensuring `prod.keys` and `title.keys` contents are never logged, printed, or leaked, and parsing untrusted or malformed NSP/NCA/IVFC containers.
- **Dependency & release supply chain** (`tools/fetch_deps.py`, `tools/make_release.py`, optional NVIDIA DLSS retrieval): checksum/SHA-256 verification and build artifact integrity.
- **Host runtime boundary** (`runtime/core/`, `runtime/mlb/`, `runtime/gfx/`): filesystem/path-normalization escapes out of mounted game or profile directories (e.g., `runtime/core/fs_host.c`) and memory-safety vulnerabilities in host-side services (`runtime/mlb/services.c`, `swkbd.c`, `hid.c`).

### Out of Scope (for Security Advisories)

- Normal game bugs, crashes, or graphics/audio issues — please report those as regular [GitHub Issues](https://github.com/sam110411/mlbts-native/issues) (with `logs/mlb.log`) rather than private security reports, unless they allow escaping the host filesystem or runtime boundary.
- Online play, Diamond Dynasty, or Nintendo/Sony network services (explicitly out of scope; see [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md)).
- Requests for encryption keys, game dumps, or assistance with piracy.
