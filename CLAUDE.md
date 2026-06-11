# Marcedit — Claude Code Instructions

## Project Overview

SwiftUI macOS PDF text editor with a Python (PyMuPDF) XPC backend.

## Build

```bash
xcodebuild build -scheme MarceditUITests -destination 'platform=macOS'
```

Only scheme: `MarceditUITests` (includes the main app target `Marcedit`).

## Visual Testing — Self-Service Loop

After making changes to the Python backend (`Sources/Marcedit/python_site/editor_pkg/`), run the visual test harness to verify edits render correctly:

### Quick: Python visual harness (headless, no GUI)

```bash
tests/run_visual_tests.sh python
```

This runs real-world PDF edits headlessly and produces:
- `tests/visual_edit_harness_report/results.json` — structured results
- `tests/visual_edit_harness_report/report.html` — HTML report with before/after images
- Per-edit PNG files in subdirectories

### Full: XCUITest visual report (requires display)

```bash
tests/run_visual_tests.sh xcui
```

This launches the app, drives UI edits, and produces:
- `/tmp/marcedit_visual_report/visual_report.json` — structured results
- `/tmp/marcedit_visual_report/visual_report.html` — HTML report
- Per-case PNG files in subdirectories

### Summary only (no re-run)

```bash
tests/run_visual_tests.sh summary
```

Prints a text summary of the last run's results to stdout.

### Self-Correction Loop

1. Run `tests/run_visual_tests.sh python`
2. Read the text summary for failures
3. For visual inspection, use the Read tool on the PNG paths shown in the summary (crop images show the changed region)
4. Check for: garbled text, font mismatch, collisions, misalignment
5. Fix the source code in `Sources/Marcedit/python_site/editor_pkg/`
6. Re-run and verify

### Python unit tests

```bash
pytest tests/test_editor_core.py tests/test_reflow_synthesizer.py tests/test_performance_regression.py tests/test_scrub_annotations.py -v
```

## Key Directories

- `Sources/Marcedit/python_site/editor_pkg/` — Python backend (core.py, core_xpc.py, reflow.py)
- `Sources/Marcedit/Views/` — SwiftUI views
- `MarceditUITests/MarceditUITestsUITests/` — XCUITest infrastructure
- `tests/` — Python tests, visual harness, corpus generator
- `ignored-resources/sample-files-marcedit/` — real-world test PDFs

## Preferences

- Do not auto-commit; always ask before committing.
