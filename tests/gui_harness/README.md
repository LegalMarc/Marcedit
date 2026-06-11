# Marcedit GUI Automation Test Harness

Complete visual testing framework for detecting UX issues in the Marcedit editing workflow.

## What This Framework Does

This test harness can **visually detect** GUI problems including:

- ✅ **Window jumping** - Unexpected window position changes
- ✅ **Preview toggle issues** - Document shifts when toggling preview
- ✅ **Edit window positioning** - Edit window appearing in wrong location
- ✅ **Text selection problems** - Selection highlighting issues
- ✅ **Document movement** - Unexpected scrolling or shifting during edits
- ✅ **Layout instability** - Elements moving around unexpectedly
- ✅ **UI responsiveness** - Freezes, lag, spinning beach ball
- ✅ **Frame-by-frame analysis** - Captures every visual step for diagnosis

## Files Overview

```
tests/gui_harness/
├── __init__.py                  # Package init
├── observer.py                   # Screenshot capture & visual observation
├── interactions.py               # AppleScript UI interactions (click, type, etc)
├── responsiveness.py             # Responsiveness & layout stability testing
├── latency_diagnostic.py         # AppleScript overhead analysis
├── visual_editing_workflow.py    # Full automated workflow (file open → edit)
├── live_editing_test.py          # Live test (assumes PDF already open) ⭐
├── run_editing_test.sh           # Helper script to run tests
└── README.md                     # This file
```

## Quick Start - Testing the Editing Workflow

### Option 1: Live Editing Test (Recommended)

Tests the actual editing experience with a PDF you have open:

```bash
# 1. Open Marcedit
# 2. Load a PDF document
# 3. Run the test
./tests/gui_harness/run_editing_test.sh
```

Or directly:
```bash
python3 -m tests.gui_harness.live_editing_test
```

This will:
1. Click in the document to select text
2. Double-click to select a word
3. Type replacement text
4. Save the edit
5. Toggle preview OFF then ON
6. **Visually detect any window jumps or document shifts**
7. Generate an HTML report with screenshots at every step

### Option 2: Full Automated Workflow

Complete end-to-end test including file opening:

```bash
python3 -m tests.gui_harness.visual_editing_workflow path/to/your.pdf
```

### Option 3: Responsiveness Testing

Test for freezes, lag, and UI sluggishness:

```bash
python3 -m tests.gui_harness.responsiveness
```

## Understanding Test Results

### Visual Reports

Each test generates an HTML report with:
- **Before/After screenshots** for every action
- **Detected issues** with visual evidence
- **Window position tracking** showing unexpected movement
- **Severity ratings**: Critical > Major > Minor

### Issue Types

| Issue Type | What It Means | Example |
|------------|---------------|---------|
| `window_jump` | Main window moved unexpectedly | Window shifted 192px left during typing |
| `preview_shift` | Document jumped when toggling preview | PDF content moved 50px when preview toggled |
| `element_jump` | UI element moved without user action | Edit button shifted position |
| `layout_shift` | Multiple elements moved (unstable layout) | Whole toolbar shifted down |
| `missing_element` | Expected UI element not found | Edit window didn't appear after selection |

### Pass/Fail Criteria

- **PASS**: No critical or major issues
- **FAIL**: One or more critical/major issues detected

Thresholds:
- **Critical**: > 50px unexpected movement
- **Major**: 20-50px unexpected movement
- **Minor**: 5-20px drift (acceptable)

## What We've Discovered

### Latency Analysis

After testing, we found:
- **AppleScript overhead**: ~310ms per click action
- **Screenshot capture**: ~560ms per capture
- **Click response (app only)**: ~100ms (excellent)

The Marcedit app itself is responsive. Most latency comes from the macOS accessibility APIs.

### Known Issues from Initial Tests

1. **Window movement during typing** (MAJOR)
   - Window shifted 192px horizontally during text input
   - Detected in step 08_text_typed
   - See: `/tmp/marcedit_editing_workflow/workflow_report.html`

## Advanced Usage

### Custom Test Scenarios

You can create custom tests for specific workflows:

```python
from tests.gui_harness import interactions, observer

# Example: Test a specific button click sequence
def test_my_workflow():
    # Click "Add PDF" button
    interactions.click_button("AddPDFButton", "Marcedit")

    # Capture before/after
    before = observer.capture_window("Marcedit")

    # Do action
    interactions.press_key('s', modifiers=['command'])

    after = observer.capture_window("Marcedit")

    # Compare for changes
    diff = observer.compare_screenshots(before, after)
    print(f"Visual change detected: {not diff['identical']}")
```

### Adding Accessibility Identifiers

To make testing more reliable, add accessibility identifiers to SwiftUI views:

```swift
Button("Save") {
    // ...
}
.accessibilityIdentifier("SaveButton")

TextField("Enter text", text: $text)
    .accessibilityIdentifier("EditTextField")
```

Then test with:
```python
interactions.click_button("SaveButton")
```

### Frame-by-Frame Capture

For detailed analysis of animations or transitions:

```python
from tests.gui_harness.observer import rapid_capture

# Capture 30 frames at 30fps during an action
frames = rapid_capture(
    app_name="Marcedit",
    count=30,
    interval=0.033  # ~30fps
)

# Frames are saved as PNG images for analysis
```

## Troubleshooting

### "AppleScript error: Can't get process"
- Grant Terminal/IDE accessibility permissions in System Settings → Privacy & Security → Accessibility

### "Screen Recording permission denied"
- Grant screen recording permission in System Settings → Privacy & Security → Screen Recording
- May need to restart Terminal after granting

### PDF doesn't load in automated tests
- Use `live_editing_test.py` instead - manually open PDF first
- File dialog automation is complex due to macOS sandboxing

### Window position shows (0, 0)
- App might not be frontmost - test calls `activate_app()` automatically
- Check if multiple windows are open - tests use "window 1"

## Next Steps

To comprehensively test your specific UX issues:

1. **Identify specific problematic interactions**
   - What exact steps trigger the issue?
   - When does the window jump?
   - What preview toggle behavior is wrong?

2. **Create targeted test scenarios**
   - Modify `live_editing_test.py` to match your workflow
   - Add specific assertions for your issues

3. **Run tests repeatedly**
   - Some issues may be timing-dependent
   - Run multiple times to catch intermittent problems

4. **Review visual evidence**
   - Check HTML reports for frame-by-frame analysis
   - Look for patterns in when issues occur

## Example Output

```
======================================================================
LIVE EDITING WORKFLOW TEST
======================================================================

[1/10] Capturing baseline state...
  Window at (307, 33)
[2/10] Clicking in document at (507, 333)...
[3/10] Double-clicking to select word...
[4/10] Edit window should be visible...
  ⚠️  ISSUE: Window jumped 192px during typing
[5/10] Typing replacement text 'MODIFIED'...
...

======================================================================
TEST COMPLETE
======================================================================

Result: ❌ FAIL
Issues: 0 critical, 1 major, 0 minor

📊 Report: /tmp/marcedit_live_editing/editing_test_report.html
```

## Contributing

To add new test scenarios:

1. Create new test file in `tests/gui_harness/`
2. Use modules: `observer`, `interactions`, `responsiveness`
3. Follow pattern from `live_editing_test.py`
4. Generate HTML report with visual evidence

## Support

Issues? Questions? Check:
- Visual reports (HTML files) for detailed evidence
- JSON results files for programmatic analysis
- Screenshots directory for manual inspection
