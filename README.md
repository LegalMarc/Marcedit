# Marcedit

A native macOS PDF text editor that edits text **in place** — preserving the original
fonts, layout, and structure of a document — built with SwiftUI on top of a Python
([PyMuPDF](https://pymupdf.readthedocs.io/)) backend running in an isolated XPC process.

> **Privacy by design:** Marcedit never connects to the Internet. All processing happens
> locally on your machine.

## Features

- **In-place text editing** with automatic font detection and matching
- **Reflow** of edited lines and paragraphs to keep layout intact
- **Metadata tools** — view and scrub document metadata
- **Secure erase** and **vector flatten** for sanitizing sensitive PDFs
- Keyboard-driven workflow with zoom, nudge, kerning, and size controls

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
