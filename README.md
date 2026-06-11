# Marcedit

A native macOS PDF text editor that edits text **in place** — preserving the original
fonts, layout, and structure of a document — built with SwiftUI on top of a Python
([PyMuPDF](https://pymupdf.readthedocs.io/)) backend running in an isolated XPC process.

> ⚠️ **Early beta.** Marcedit is under active development and may contain bugs, including
> ones that can alter or damage a PDF. **Always keep a backup of any document you edit.**
> It is provided as-is with **no warranty of any kind** (see [LICENSE](LICENSE)) and is not
> intended for production or mission-critical work yet.

> **Privacy by design:** Marcedit never connects to the Internet. All processing happens
> locally on your machine.

## Download

Grab the latest signed & notarized build from the
[**Releases**](https://github.com/LegalMarc/Marcedit/releases) page.

1. Download the `.dmg`, open it, and drag **Marcedit** to your Applications folder.
2. Launch it — the build is Developer-ID signed and Apple-notarized, so it opens without
   Gatekeeper warnings.

**Requirements:** macOS 14.0 (Sonoma) or later, on an **Apple Silicon (M-series)** Mac.
This beta is arm64-only; Intel Macs are not supported yet.

## Features

- **In-place text editing** — click a line, edit it, and keep the original font and layout
- **Automatic font detection & matching** with confidence scoring, plus manual font search
- **Fine positioning** — nudge, resize, and kern edited text in sub-point increments
- **Styling** — bold / italic / underline / strikethrough, text color, and alignment detection
- **Live preview** with **collision detection** (warns when new text overlaps existing content)
- **Reflow** of edited lines and paragraphs to keep layout intact
- **Document tools** — view & scrub metadata, vector-flatten, and DoD-style secure erase
- **Multi-document** sidebar, undo/redo, per-document zoom, and PDF dark mode

See [`docs/documentation/FEATURES.md`](docs/documentation/FEATURES.md) for the full list.

## Beta status & caveats

Marcedit is an early beta — see the warning above. A few things to know:

- **Vector Flatten** is irreversible by design — run it only on a copy.
- **Secure Erase** permanently destroys the target file; there is no undo.
- Font matching is strong but not perfect on unusual or heavily-subsetted fonts — always
  check the live preview before saving.
- Keep backups. Report bugs via [Issues](https://github.com/LegalMarc/Marcedit/issues).

## Architecture

| Layer | Technology |
|-------|------------|
| UI | SwiftUI (macOS) |
| Backend | Python 3.11 + PyMuPDF, vendored and run over XPC |
| IPC | Cross-process XPC for isolation between the UI and the PDF engine |

The Python runtime is vendored under `Sources/Marcedit/python_site/` so the app builds
and runs without an external Python installation.

## Build

```bash
xcodebuild build -scheme MarceditUITests -destination 'platform=macOS'
```

`MarceditUITests` is the primary scheme and includes the main `Marcedit` app target.

## Tests

```bash
# Python unit tests
python3 -m pytest tests/test_editor_core.py tests/test_reflow_synthesizer.py \
  tests/test_performance_regression.py -v

# Visual edit harness (headless)
tests/run_visual_tests.sh python
```

See [`docs/`](docs/) for architecture notes, the testing guide, and developer
documentation.

## License

[MIT](LICENSE) © Marc Mandel
