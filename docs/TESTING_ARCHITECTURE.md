# Marcedit Testing Architecture

## Overview

Marcedit employs a multi-layered testing strategy to ensure the robustness of its PDF editing capabilities. This document outlines the testing infrastructure, how to run tests, and how to extend the test suite.

## 1. Core Unit Tests (`tests/`)

The core logic for PDF manipulation, text reflow, and font synthesis is written in Python and tested using `pytest`.

### Key Test Files

| File | Scope | Description |
|------|-------|-------------|
| `test_editor_core.py` | Low-level API | Tests `core.py` functions: text replacement, basic geometry, and helper utilities. |
| `test_reflow_synthesizer.py` | Reflow Engine | Validates the complex `reflow.py` logic: line breaking, expansion/contraction, and spatial integrity. |
| `test_font_extraction.py` | Font Analysis | Verifies accurate extraction of font colors, sizes, and mapping to replacement fonts. |
| `test_redaction_cleanup.py` | Redaction | Ensures sensitive text is physically removed from the PDF stream, not just covered. |
| `pipeline_test.py` | Integration | End-to-end test of the python pipeline (open -> edit -> save) without the UI. |

### Running Core Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all core tests
pytest tests/ -v

# Run specific suite
pytest tests/test_reflow_synthesizer.py
```

---

## 2. Visual Verification Harness (`tests/visual_harness/`)

The Visual Harness is an advanced testing tool designed to catch regression in rendering quality that unit tests might miss. It generates hundreds of variations of edits to visually clear documents.

### Architecture

- **Manifest**: `test_manifest.json` defines all test cases.
- **Runner**: `run_tests.py` executes edits on sample PDFs.
- **Reporting**: Generates PDF reports highlighting before/after states.

### Running the Harness

```bash
cd tests/visual_harness

# Run all tests
python run_tests.py --run

# Run specific test cases
python run_tests.py --run --tests TC-001,TC-002

# Generate Visual Report
python run_tests.py --report
```

### Safety Note
Input PDFs for the harness are stored in `ignored-resources/` to prevent leakage of proprietary documents.

---

## 3. Optical Verification Integration

We employ "Optical Verification" to ensure that edits don't just "not crash" but actually look correct.

- **Collision Detection**: The reflow engine actively detects if new text overlaps existing text.
- **Ink Analysis**: Tests verify that pixels are actually drawn where expected (not invisible text).

---

## 4. Swift Application Tests

The macOS application wrapper is tested using XCTest.

- **Target**: `MarceditTests`
- **Scope**:
    - `DocumentCoordinator` state management
    - XPC Bridge stability
    - Integration with Python backend

```bash
# Run Swift tests
swift test --filter MarceditTests
```
