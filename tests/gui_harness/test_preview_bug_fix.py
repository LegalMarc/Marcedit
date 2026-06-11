#!/usr/bin/env python3
"""
Automated test to verify the preview bug fix.

Bug: When Preview is toggled, edited text was being overwritten with original text.
Fix: Changed restoreState(from: doc) to restoreState(from: documents[idx])

This test:
1. Opens a PDF with known text
2. Selects text and opens edit dialog
3. Changes the text to a known value
4. Toggles Preview ON
5. Reads the text field value and verifies it wasn't reverted
"""

import sys
import time
import os
import subprocess
import tempfile

# Add gui_harness to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import interactions

APP_NAME = "Marcedit"
MODIFIED_TEXT = "PREVIEW_BUG_FIXED_12345"


def create_test_pdf(path):
    """Create a simple test PDF with known text."""
    script = f'''
import fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text((50, 700), "Hello World", fontsize=12, fontname="helv")
page.insert_text((50, 680), "Test Line 2", fontsize=12, fontname="helv")
doc.save("{path}")
doc.close()
print("created")
'''
    result = subprocess.run(['python3', '-c', script], capture_output=True, text=True)
    return 'created' in result.stdout


def launch_app_with_pdf(pdf_path):
    """Launch Marcedit with a specific PDF."""
    app_path = ".build/release/Marcedit"

    # Check if app exists
    if not os.path.exists(app_path):
        print(f"  ❌ App not found at: {app_path}")
        print("  Run 'swift build -c release' first")
        return False

    # Kill existing instance
    subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
    time.sleep(0.5)

    # Launch with test PDF argument
    env = os.environ.copy()
    env['TESTING'] = '1'
    env['DISABLE_AUTOSAVE'] = '1'

    subprocess.Popen(
        [app_path, '--run-ui-tests', f'--test-pdf-path={pdf_path}'],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Wait for app to launch
    for i in range(10):
        time.sleep(1)
        script = 'tell application "System Events" to return name of every process'
        result = interactions.run_applescript(script)
        if APP_NAME in result:
            return True

    return False


def wait_for_pdf_loaded(timeout=15):
    """Wait for PDF to be loaded in the viewer."""
    for i in range(timeout):
        # Check if PDF viewer has content
        script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            if (count of windows) > 0 then
                set uiElements to entire contents of window 1
                repeat with elem in uiElements
                    try
                        if description of elem is "PDFViewer" then
                            return "loaded"
                        end if
                    end try
                end repeat
            end if
        end try
    end tell
end tell
return "waiting"
'''
        result = interactions.run_applescript(script)
        if 'loaded' in result:
            return True
        time.sleep(1)
    return False


def double_click_on_text():
    """Double-click on PDF text to open edit dialog."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.3)

    # Get window center and click on text area
    pos = interactions.get_window_position(APP_NAME)
    size = interactions.get_window_size(APP_NAME)

    if not pos or not size:
        return False

    # Click in the upper-left area where "Hello World" should be
    click_x = pos[0] + 250  # Left side of window content
    click_y = pos[1] + 150  # Upper area

    # Double-click
    script = f'''
tell application "System Events"
    click at {{{click_x}, {click_y}}}
    delay 0.1
    click at {{{click_x}, {click_y}}}
end tell
'''
    interactions.run_applescript(script)
    return True


def wait_for_edit_dialog(timeout=5):
    """Wait for edit dialog to appear."""
    for i in range(timeout):
        script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Look for text field or text area
            if (count of text fields of window 1) > 0 then
                return "found"
            end if
            if (count of text areas of window 1) > 0 then
                return "found"
            end if
        end try
    end tell
end tell
return "waiting"
'''
        result = interactions.run_applescript(script)
        if 'found' in result:
            return True
        time.sleep(1)
    return False


def get_edit_text_value():
    """Get the current value of the edit text field."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Try text field first
            if (count of text fields of window 1) > 0 then
                return value of text field 1 of window 1
            end if
            -- Try text area
            if (count of text areas of window 1) > 0 then
                return value of text area 1 of window 1
            end if
        end try
    end tell
end tell
return ""
'''
    return interactions.run_applescript(script)


def set_edit_text_value(new_text):
    """Set the edit text field to a new value."""
    # Select all and type new text
    interactions.press_key('a', modifiers=['command'], app_name=APP_NAME)
    time.sleep(0.1)
    interactions.type_text(new_text, app_name=APP_NAME)
    time.sleep(0.3)


def toggle_preview():
    """Toggle the Preview checkbox."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Try to find checkbox with "Preview" in name
            set allCheckboxes to every checkbox of window 1
            repeat with cb in allCheckboxes
                try
                    if name of cb contains "Preview" then
                        click cb
                        return "clicked"
                    end if
                end try
            end repeat

            -- Try by description/identifier
            click (first checkbox whose description contains "Preview") of window 1
            return "clicked"
        on error
            -- Try all checkboxes
            if (count of checkboxes of window 1) > 0 then
                click checkbox 1 of window 1
                return "clicked_first"
            end if
        end try
    end tell
end tell
return "not_found"
'''
    result = interactions.run_applescript(script)
    return 'clicked' in result


def capture_screenshot(name):
    """Capture a screenshot for debugging."""
    output_dir = os.path.join(os.path.dirname(__file__), "test_output")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{name}.png")
    subprocess.run(['screencapture', '-x', filepath], capture_output=True)
    return filepath


def main():
    print("=" * 70)
    print("PREVIEW BUG FIX VERIFICATION TEST")
    print("=" * 70)
    print()
    print("This test verifies that edited text is NOT overwritten when")
    print("toggling Preview ON. (Fix in EditorViewModel.swift line 665)")
    print()

    # Create test PDF
    pdf_path = tempfile.mktemp(suffix='.pdf')

    try:
        print("[1/7] Creating test PDF...")
        if not create_test_pdf(pdf_path):
            print("  ❌ FAILED: Could not create test PDF")
            return False
        print(f"  ✓ Created: {pdf_path}")

        # Launch app
        print("[2/7] Launching Marcedit with test PDF...")
        if not launch_app_with_pdf(pdf_path):
            print("  ❌ FAILED: Could not launch Marcedit")
            return False
        print("  ✓ Marcedit launched")

        # Wait for PDF to load
        print("[3/7] Waiting for PDF to load...")
        time.sleep(2)  # Give app time to initialize
        if not wait_for_pdf_loaded():
            print("  ⚠ Could not confirm PDF loaded - continuing anyway")
        else:
            print("  ✓ PDF loaded")

        capture_screenshot("01_pdf_loaded")

        # Double-click to open edit dialog
        print("[4/7] Opening edit dialog (double-click on text)...")
        double_click_on_text()
        time.sleep(1)

        if not wait_for_edit_dialog():
            print("  ⚠ Edit dialog may not have opened - trying again...")
            double_click_on_text()
            time.sleep(1)

        capture_screenshot("02_edit_dialog")
        print("  ✓ Attempted to open edit dialog")

        # Get original text
        print("[5/7] Recording original text and modifying it...")
        original_text = get_edit_text_value()
        print(f"  Original text: '{original_text[:50]}...' " if len(original_text) > 50 else f"  Original text: '{original_text}'")

        # Set modified text
        set_edit_text_value(MODIFIED_TEXT)
        time.sleep(0.5)

        text_after_edit = get_edit_text_value()
        print(f"  Modified text: '{text_after_edit}'")
        capture_screenshot("03_after_edit")

        if MODIFIED_TEXT not in text_after_edit:
            print("  ⚠ Warning: Modified text may not have been set correctly")

        # Toggle Preview
        print("[6/7] Toggling Preview ON...")
        if toggle_preview():
            print("  ✓ Preview toggled")
        else:
            print("  ⚠ Could not confirm Preview toggle")

        time.sleep(2)  # Wait for preview to render
        capture_screenshot("04_after_preview")

        # CRITICAL CHECK: Read text after preview
        print("[7/7] Verifying text was preserved after preview toggle...")
        text_after_preview = get_edit_text_value()
        print(f"  Text after preview: '{text_after_preview}'")

        capture_screenshot("05_verification")

        print()
        print("=" * 70)
        print("TEST RESULTS")
        print("=" * 70)

        # Determine pass/fail
        if MODIFIED_TEXT in text_after_preview:
            print()
            print("  ✅ PASS: Text was preserved after preview toggle!")
            print(f"     Expected: '{MODIFIED_TEXT}'")
            print(f"     Got:      '{text_after_preview}'")
            print()
            print("  The preview bug fix is working correctly.")
            return True
        elif text_after_preview == original_text:
            print()
            print("  ❌ FAIL: Text REVERTED to original after preview toggle!")
            print(f"     Expected: '{MODIFIED_TEXT}'")
            print(f"     Got:      '{text_after_preview}' (original)")
            print()
            print("  BUG NOT FIXED: restoreState is using stale document copy.")
            return False
        else:
            print()
            print("  ⚠ INCONCLUSIVE: Text changed but doesn't match expected")
            print(f"     Expected: '{MODIFIED_TEXT}'")
            print(f"     Got:      '{text_after_preview}'")
            print()
            print("  Check screenshots in test_output/ for manual verification.")
            return False

    finally:
        # Cleanup
        print()
        print("Cleaning up...")
        subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        print("Done.")


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
