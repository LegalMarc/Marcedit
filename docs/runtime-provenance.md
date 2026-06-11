# Marcedit Runtime Provenance

Last reviewed: 2026-05-13

## Bundled CPython

- Location: `Sources/Marcedit/Frameworks/Python.framework`
- Bundled version: 3.11.15, from `Sources/Marcedit/Frameworks/Python.framework/Versions/3.11/Resources/Info.plist`
- Current upstream 3.11 security release observed during this review: 3.11.15, released 2026-03-03, listed on `https://www.python.org/downloads/release/python-31115/`
- Source: local Homebrew `python@3.11` framework from `/opt/homebrew/opt/python@3.11/Frameworks/Python.framework`
- Runtime policy: arm64-only for public beta. Python.org no longer publishes full macOS binary installers for post-3.11.9 security-only 3.11 releases, so the public-beta framework is sourced from the local Homebrew arm64 security build.
- Relocation: framework load commands and rpaths are rewritten away from `/opt/homebrew`; the verifier fails if the framework binary, embedded `Resources/Python.app` launcher, native extension modules, or bundled dylibs retain `/opt/homebrew` references.
- Bundled native dependencies: OpenSSL 3.6.2, SQLite 3.53.0, liblzma, and libmpdec are copied into `Python.framework/Versions/3.11/lib` and signed with the framework.
- Helper scripts with Homebrew shebangs (`pip`, `idle`, `pydoc`, `2to3`, and `python3.11-config`) are removed from the bundled framework; the remaining `bin/python3.11` executable is relocated to the in-framework `Python` library.
- Homebrew `sitecustomize.py` is removed from the bundled framework so interpreter startup cannot rewrite `sys.path`, `sys.prefix`, or `sys.executable` back to `/opt/homebrew`.
- Signing note: the framework is ad-hoc signed with hardened runtime for local verification, while the embedded `Resources/Python.app` launcher is ad-hoc signed without hardened runtime so the bundled command-line interpreter can load the in-framework `Python` library during smoke tests. Public distribution still requires Developer ID signing and notarization through the release lane.
- Framework smoke test: the bundled interpreter imports `ssl`, `sqlite3`, `lzma`, and `decimal` from both the source framework and the assembled Release app bundle with `PYTHONDONTWRITEBYTECODE=1` so validation does not mutate signed framework contents.

## Vendored Python Packages

- Location: `Sources/Marcedit/python_site`
- Lockfile: `runtime-requirements-lock.txt`
- Drift check: `python3 Scripts/verify_runtime_dependencies.py`
- Vulnerability audit: `pip-audit --path Sources/Marcedit/python_site --strict`
- Native architecture policy: arm64-only for public-beta runtime. Several vendored native wheels, including Pillow, are arm64-only, so Release builds are constrained to arm64 until universal2 wheels are deliberately vendored and validated. The Release shell build passes `swift build --arch arm64`, and app verification checks that `Contents/MacOS/Marcedit` contains arm64.
- Integrity check: `Scripts/verify_runtime_dependencies.py` validates package versions, wheel `RECORD` SHA-256 hashes, absence of unexpected runtime files outside explicit first-party exceptions, and required native Mach-O architecture.

Vendored package versions after the 2026-05-13 refresh:

```text
Deprecated==1.3.1
fonttools==4.61.1
lxml==6.1.0
packaging==25.0
pikepdf==10.1.0
pillow==12.2.0
PyMuPDF==1.26.7
pyobjc-core==12.1
pyobjc-framework-Cocoa==12.1
pyobjc-framework-CoreText==12.1
pyobjc-framework-Quartz==12.1
wrapt==2.0.1
```

Refresh notes:

- `lxml` was updated from 6.0.2 to 6.1.0 after `pip-audit` reported CVE-2026-41066.
- `pillow` was updated from 12.0.0 to 12.2.0 after `pip-audit` reported CVE-2026-25990 and CVE-2026-40192/CVE-2026-42308/CVE-2026-42309/CVE-2026-42310/CVE-2026-42311.
- `requirements-lock.txt` now includes `runtime-requirements-lock.txt` and keeps `reportlab==4.4.10` as a test/report harness dependency that is not vendored into the app runtime.
- The Release app target sets `ARCHS = arm64` to match the vendored native runtime.
- Vendored `__pycache__` and `.DS_Store` artifacts were removed so the runtime verifier can fail on unexpected files. The Release bundle assembly also removes these artifacts from the copied resource bundle before signing.

## Verification Commands

```bash
python3 Scripts/verify_runtime_dependencies.py
pip-audit --path Sources/Marcedit/python_site --strict
python3 Scripts/verify_release_security.py --app build/DerivedData/Build/Products/Release/Marcedit.app
```
