# Developer Guide: Font Handling & Layout Engine

## Overview
This document details the advanced font handling mechanisms in Marcedit, specifically addressing how we solve font weight regressions and handle embedded font reuse.

## The "Simulated Bold" Problem
**Issue:** When replacing text in PDFs, the new text sometimes appeared "thinner" or lighter than the original, even when using the correct font family (e.g., Calibri).

**Root Cause:**
Many PDFs do not embed the "Bold" variant of a font (e.g., `Calibri-Bold`). Instead, they embed the "Regular" font (`Calibri-Regular`) and use **PDF Operators** to artificially thicken the text.
*   **`Tr 2`**: Text Rendering Mode 2 (Fill + Stroke).
*   **`w`**: Line Width (e.g., `0.28 w`).
This "Simulated Bold" (or "Faux Bold") effect renders the character outline with a stroke, making it look bold.

Standard PyMuPDF `insert_text()` operations default to `Tr 0` (Fill only), causing the replacement text to lose this artificial weight and appear thin.

## The Solution: Simulated Bold Injection

We implemented a low-level workaround to replicate this effect.

### 1. Internal Font Name Reuse
**Function:** `_find_internal_font_name(doc, page, font_name, replacement_text)`
*   Scans `page.get_fonts()` to find the **internal resource name** (e.g., `/F1`, `/C2_0`) of the embedded font.
*   Verifies that the embedded font subset contains all necessary glyphs for the replacement text.
*   **Result:** We pass this internal name (e.g., "F1") directly to `page.insert_text(fontname="F1", ...)` instead of creating a new `fitz.Font` object. This ensures 1:1 character shape matching without creating duplicate font resources.

### 2. Stream Operator Injection (The Hack)
**Function:** `_inject_simulated_bold(page, stroke_width)`
Since PyMuPDF's high-level API doesn't expose `render_mode` or `stroke_width` for standard text insertion, we inject the raw PDF operators manually during post-processing.

**Workflow:**
1.  **Clean Contents:** `page.clean_contents()` consolidates the page into a single content stream and ensures syntax validity.
2.  **Read Stream:** We access the raw byte stream of the page.
3.  **Locate Text:** We find the specific font selection operator for our inserted text (e.g., `/F1 11 Tf`) at the end of the stream.
4.  **Inject Operators:** We insert the "Simulated Bold" operators *before* the font selection:
    ```
    0.28 w 2 Tr /F1 11 Tf ...
    ```
    *   `0.28 w`: Sets line width to 0.28 (calculated as ~2.5% of font size).
    *   `2 Tr`: Sets render mode to Fill + Stroke.
5.  **Update Stream:** We write the modified stream back to the PDF.

### Usage
This logic is triggered automatically in `replace_text_in_pdf` when:
1.  **Manual Mode** is active.
2.  The user selects **"Bold"** style in the layout panel.

```python
if manual_overrides.get('is_bold'):
    width = fontsize * 0.025
    _inject_simulated_bold(page, stroke_width=width)
```

## Debugging
If fonts appear incorrect:
1.  **Check Output Log:** Look for "Using internal font name: 'F1'" or "Applying Simulated Bold".
2.  **Verify PDF Stream:** Use `mutool` or specific Python scripts to inspect if `2 Tr` is present near the text object.
3.  **Temp Files:** Ensure temporary files aren't being deleted prematurely, which causes "Edit failed" errors.

## Verification & Troubleshooting

### How to Verify the Fix
To confirm that the "Simulated Bold" injection worked, you can inspect the raw PDF stream.
Run this Python snippet:

```python
import fitz

doc = fitz.open("path/to/output.pdf")
stream = doc[0].read_contents().decode('latin1', errors='ignore')

# Check for the magic operators at the end of the stream
if "0.28 w 2 Tr" in stream[-500:]:
    print("SUCCESS: Faux Bold operators found!")
else:
    print("FAILURE: Faux Bold operators missing.")
```

### Critical Dependencies
*   **`page.clean_contents()` is Mandatory:** The injection hack relies on `page.clean_contents()` to consolidate the stream into a predictable format. Skipping this will likely cause `ValueError: bad xref` or silent failure because the targeted string `/F1 11 Tf` won't be found where expected.
*   **Regex Flexibility:** The injector uses regex `(/[a-zA-Z0-9_]+ [0-9\.]+ Tf)` to find the font selection. If PyMuPDF changes its output format (e.g., extra spaces), this regex might need adjustment.

### Known Limitations
*    **Stroke Width Calculation:** Currently hardcoded to `fontsize * 0.025`. This matches the ~11pt / 0.28w ratio observed in Calibri. Other fonts might need different ratios.
*   **Manual Trigger Only:** Currently, this only activates if `is_bold` is manually set. A future improvement could auto-detect if the original text used `Tr 2` and auto-apply it.
