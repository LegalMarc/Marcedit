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

## Pre-commit Hook

`Scripts/precommit_checks.sh` is the tracked pre-commit hook. It asserts Python 3.11
(the version targeted by the bundled framework and CI) and then runs the critical unit
tests. Install it once per clone:

```bash
ln -sf "$(git rev-parse --show-toplevel)/Scripts/precommit_checks.sh" \
       "$(git rev-parse --show-toplevel)/.git/hooks/pre-commit"
```

The check hard-fails under any non-3.11 interpreter with an actionable message. If you
see the mismatch error, activate a 3.11 venv (`source .venv/bin/activate`) before
committing.

## Release

Use `Scripts/sign_notarize_release.sh` — the only supported release path. See `docs/RELEASE_CHECKLIST.md`.

## Preferences

- **Landing work (commit / push / merge).** Once a run is finished, you are authorized to
  commit the completed work, push the branch, and open + merge a PR to `main` to leave the
  tree clean — without asking first — *as long as you see no reason not to*. Reasons not to
  (stop and ask instead): tests/CI not green, an unresolved failure or regression, an
  ambiguous or risky change that needs my call, anything irreversible beyond a normal merge,
  or work that isn't actually complete. Prefer the PR flow (push → `gh pr create` →
  `gh pr merge`, squash) and confirm CI is green before merging. When genuinely in doubt,
  ask. (This relaxes the former "always ask before committing" rule, which you can still
  fall back to for speculative mid-run commits.)
