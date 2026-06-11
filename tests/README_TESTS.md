# MarcEdit PDF Editor - Test Suite

## Overview

Comprehensive unit tests for the critical PDF editing functions. These tests verify the bug fixes and improvements made during the code review session.

## Test Files

### 1. `test_editor_core.py`
Tests for core functions in `core.py`:
- `_get_reference_char_metrics()` - Character measurement and selection
- `_calculate_precise_redaction_rect()` - Precise redaction rectangle calculation
- Baseline calculation logic
- Font scaling logic
- Descender/ascender ratio calculations
- Input validation guards
- Edge cases and error handling

**Test Classes:**
- `TestReferenceCharMetrics` - 8 tests
- `TestPreciseRedactionRect` - 5 tests
- `TestBaselineCalculations` - 2 tests
- `TestFontScalingLogic` - 3 tests
- `TestDescenderRatio` - 4 tests
- `TestEdgeCases` - 4 tests
- `TestArrayBoundsPrevention` - 2 tests
- `TestInputValidation` - 4 tests
- `TestIntegrationScenarios` - 2 tests

**Total:** 34 tests

### 2. `test_reflow_synthesizer.py`
Tests for reflow engine and synthesizer functions:
- `_get_line_structure()` - Line parsing and structure detection
- `reflow_line()` - Main reflow function
- Adaptive tolerance logic
- Collision detection
- Width calculations with kerning
- Visual copy validation
- Synthesis parameter validation
- Character-specific side bearings
- Error recovery mechanisms

**Test Classes:**
- `TestGetLineStructure` - 4 tests
- `TestReflowLine` - 5 tests
- `TestAdaptiveTolerance` - 4 tests
- `TestCollisionDetection` - 3 tests
- `TestWidthCalculations` - 3 tests
- `TestVisualCopyValidation` - 2 tests
- `TestSynthesisParameters` - 3 tests
- `TestCharacterSideBearings` - 1 test
- `TestErrorRecovery` - 2 tests
- `TestMarginCalculations` - 2 tests
- `TestIntegrationReflowScenarios` - 2 tests

**Total:** 31 tests

### 3. `test_performance_regression.py`
Performance regression tests for the Week 7–8 caching layer:
- `normalize_unicode()` — LRU-cache hit/miss/eviction accounting
- `normalize_text_for_matching()` — hit/miss, `preserve_case` arg caching
- `normalize_special_chars()` — empty-string edge case, stability
- `_get_cached_font()` — cold load, warm hit identity, eviction at MAX, error recovery
- `get_cache_stats()` — required keys, live accounting, font/normalise counts
- Timing regressions — warm cache measurably faster than cold for all 3 normalise fns
- Batch GC wiring — `batch_replace`, `regex_replace`, `apply_template` each call `gc.collect()` in their `finally` block (early-exit paths verified not to call it unnecessarily)
- Cache correctness — cached and freshly-computed results are identical
- Sanity configuration — cache max sizes within expected bounds

**Test Classes:**
- `TestNormalizeUnicodeCaching` — 7 tests
- `TestNormalizeTextForMatchingCaching` — 4 tests
- `TestNormalizeSpecialCharsCaching` — 3 tests
- `TestFontObjectCache` — 9 tests
- `TestGetCacheStats` — 7 tests
- `TestTimingRegressions` — 3 tests
- `TestBatchFunctionGC` — 5 tests
- `TestCacheCorrectness` — 5 tests
- `TestCacheSanityConfiguration` — 6 tests
- `TestCacheStatsIntegration` — 3 tests

**Total:** 52 tests

### 4. `test_week6_collision.py`
Visual collision detection tests (ratio-based severity levels):
- Before/after pixmap comparison
- Collision severity thresholds
- False-positive rejection

**Total:** 12 tests

### 5. `test_week6_unicode.py`
Unicode normalization function tests:
- NFC/NFD/NFKC/NFKD normalization
- Ligature decomposition and restoration
- Special character handling
- Edge cases and invalid input

**Total:** 10 tests

### 6. `test_security.py`
Security boundary tests:
- Page bounds validation (negative page, out-of-bounds)
- Input sanitization
- Replace block with spans page bounds

**Total:** 50 tests

### 7. `test_real_world_pdfs.py` (CLI harness, not pytest)
Real-world PDF editing smoke test — run as standalone script:
```bash
python3 tests/test_real_world_pdfs.py
```
Tests 10 edits per PDF across all sample files.

### 8. Visual Edit Harness (`visual_edit_harness.py`)
Headless PDF edit + visual verification pipeline:
```bash
python3 tests/visual_edit_harness.py
```
Renders before/after PNGs, computes pixel diffs, generates HTML report.
Output: `tests/visual_edit_harness_report/`

### 9. XCUITest Visual Report
Swift UI test plus post-XCTest report rendering (requires display):
- `RealWorldEditTests.testVisualReport_AllCases()` — runs all corpus cases, saves edited PDFs, and emits per-case JSON manifests
- `tests/render_xcui_visual_report.py` — renders before/after PNGs, crops, JSON, and HTML after `xcodebuild test` exits
- Output: `/tmp/marcedit_visual_report/` (HTML + JSON + PNGs)

## Running the Tests

### Prerequisites

Install pytest:
```bash
pip3 install pytest PyMuPDF
```

Or using the system Python with Homebrew on macOS:
```bash
# You may need to use --user flag or virtual environment
python3 -m pip install --user pytest PyMuPDF
```

### Run All Tests

```bash
# From project root

# Run all pytest-compatible tests
pytest tests/test_editor_core.py tests/test_reflow_synthesizer.py \
       tests/test_performance_regression.py tests/test_week6_collision.py \
       tests/test_week6_unicode.py tests/test_security.py -v

# Run visual harness (headless, no GUI)
tests/run_visual_tests.sh python

# Run just the summary of last visual test run
tests/run_visual_tests.sh summary
```

### Run Specific Test Files

```bash
# Test core functions only
pytest tests/test_editor_core.py -v

# Test reflow/synthesizer functions only
pytest tests/test_reflow_synthesizer.py -v
```

### Run Specific Test Classes

```bash
# Run only baseline calculation tests
pytest tests/test_editor_core.py::TestBaselineCalculations -v

# Run only adaptive tolerance tests
pytest tests/test_reflow_synthesizer.py::TestAdaptiveTolerance -v
```

### Run Specific Tests

```bash
# Run a single test
pytest tests/test_editor_core.py::TestBaselineCalculations::test_baseline_from_top_correct -v

# Run all tests containing "baseline" in the name
pytest tests/ -k baseline -v
```

## Test Coverage

The test suite covers:

### Bug Fixes Verified ✅
1. **Baseline Estimation Bug** - Verified baseline is calculated from top, not bottom
2. **Descender Ratio Bug** - Verified correct 0.7/0.3 ratios are used
3. **Array Bounds Bug** - Verified loops stop early to prevent overflow

### Input Validation ✅
- None/empty page handling
- Invalid rect handling
- Invalid text handling
- Invalid font_info handling
- Page number bounds checking

### Core Functionality ✅
- Character type categorization (x-height, cap-height, ascender, descender)
- Multi-character averaging for accuracy
- Adaptive tolerance by font size
- Kerning compensation
- Character-specific side bearings
- Safety margin calculations

### Edge Cases ✅
- Empty candidate lists
- Spaces and special characters
- Rect expansion amounts
- Text expansion/contraction scenarios
- Collision detection and recovery

## Expected Test Results

When all tests pass, you should see:
```
========================= test session starts ==========================
collected 207 items
...
========================= 207 passed in X.XXs ==========================
```

## Test Data

Tests create temporary PDF files using pytest's `tmp_path` fixture. These are automatically cleaned up after each test.

## Debugging Failed Tests

If a test fails, run it with verbose output:
```bash
pytest tests/test_editor_core.py::TestClassName::test_name -vv -s
```

To drop into a debugger on failure:
```bash
pytest tests/test_editor_core.py::TestClassName::test_name --pdb
```

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install pytest PyMuPDF
    pytest tests/ -v --tb=short
```

## Adding New Tests

When adding new features or fixing bugs:

1. Create a new test class or add to existing ones
2. Follow the naming pattern: `test_<functionality_being_tested>`
3. Use descriptive test names that explain what is being tested
4. Include fixtures for common setup
5. Test both success and failure cases

Example:
```python
class TestNewFeature:
    def test_basic_functionality(self, sample_page):
        """Test that basic feature works correctly."""
        result = new_function(sample_page, "input")
        assert result is not None

    def test_edge_case_handling(self):
        """Test that edge cases are handled gracefully."""
        result = new_function(None, "input")
        assert result == expected_fallback
```

## Test Maintenance

- Keep tests independent (each test should work in isolation)
- Update tests when changing function signatures
- Add new tests for new functionality
- Remove tests for deprecated features
- Maintain test coverage above 80%

## Known Limitations

These tests do NOT cover:
- Memory leak detection (requires specialized tools)
- Cross-platform font rendering (requires platform-specific tests)

For comprehensive testing, the full test pipeline is:
1. **Unit tests** (pytest) — 207+ tests for core functions
2. **Visual harness** (`visual_edit_harness.py`) — headless PDF editing + visual verification
3. **XCUITests** (`testVisualReport_AllCases`) — end-to-end UI edits plus post-test report rendering
4. **Summary** (`run_visual_tests.sh summary`) — text-based results for LLM review

## Troubleshooting

### "ModuleNotFoundError: No module named 'fitz'"
Install PyMuPDF:
```bash
pip3 install --user PyMuPDF
```

### "ImportError: No module named editor_pkg"
Make sure you're running from the project root and the path is correct.

### Tests create PDF files that aren't cleaned up
This is normal - pytest uses temporary directories that should be cleaned up automatically. If files persist, check your pytest configuration.

## Future Improvements

Potential additions to the test suite:
1. Performance benchmarks for large documents
2. Memory usage profiling
3. Stress tests with malformed PDFs
4. Cross-platform font rendering tests
5. Visual regression tests using image comparison
6. Property-based testing with Hypothesis

---

**Last Updated:** March 18, 2026
**Test Framework:** pytest 7.0+
**Python Version:** 3.8+
**Total Tests:** 207+ (pytest) + visual harness + XCUITests
