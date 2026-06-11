#!/usr/bin/env python3
"""
Automated test for preview bug fix using app's built-in test mode.

This test:
1. Launches app with --run-ui-tests --test-pdf-path to auto-load PDF
2. Clicks on PDF text to open edit dialog
3. Modifies the text
4. Toggles Preview ON
5. Verifies the modified text is preserved (not reverted)
"""

import sys
import time
import os
import subprocess
import tempfile
import signal

# Add gui_harness to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import interactions

APP_PATH = "/Users/mhm/Documents/Dev/Marcedit/.build/Marcedit.app/Contents/MacOS/Marcedit"
APP_NAME = "Marcedit"
MODIFIED_TEXT = "MODIFIED_BY_TEST"
ORIGINAL_TEXT = "CLICK_HERE_TO_EDIT"


def create_test_pdf(path):
    """Create test PDF with known text."""
    script = f'''
import fitz
doc = fitz.open()
page = doc.new_page(width=612, height=792)
# Place text where it will be visible and clickable
page.insert_text((200, 350), "{ORIGINAL_TEXT}", fontsize=16, fontname="helv")
doc.save("{path}")
doc.close()
print("created")
'''
    result = subprocess.run(['python3', '-c', script], capture_output=True, text=True)
    return 'created' in result.stdout


def capture_screenshot(name):
    """Capture screenshot."""
    output_dir = os.path.join(os.path.dirname(__file__), "test_output")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"auto_{name}.png")
    subprocess.run(['screencapture', '-x', filepath], capture_output=True)
    return filepath


def launch_app_with_test_pdf(pdf_path):
    """Launch app with test mode and PDF path."""
    # Kill any existing instance
    subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
    time.sleep(1)

    # Launch with test arguments
    proc = subprocess.Popen(
        [APP_PATH, '--run-ui-tests', f'--test-pdf-path={pdf_path}'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Wait for app to start and PDF to load
    for _ in range(10):
        time.sleep(1)
        procs = interactions.run_applescript('tell application "System Events" to return name of every process')
        if APP_NAME in procs:
            break

    time.sleep(3)  # Extra time for PDF to render
    return proc


def verify_pdf_loaded():
    """Check if PDF is loaded (no 'No Document Selected' visible)."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            set allTexts to value of every static text of window 1
            repeat with txt in allTexts
                if txt contains "No Document" then
                    return "not_loaded"
                end if
            end repeat
            return "loaded"
        on error
            return "error"
        end try
    end tell
end tell
'''
    result = interactions.run_applescript(script)
    return 'loaded' in result


def click_on_pdf_text():
    """Click on PDF text to open edit dialog."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.3)

    pos = interactions.get_window_position(APP_NAME)
    size = interactions.get_window_size(APP_NAME)
    if not pos or not size:
        return False

    print(f"  Window at {pos}, size {size}")

    # Calculate click position based on visual inspection:
    # The PDF content area is roughly centered in the right portion of the window
    # Text appears around x=700, y=430 in absolute screen coords when window is at (48, 33)
    # So relative to window: x=700-48=652, y=430-33=397
    click_x = pos[0] + 650  # Roughly where text is horizontally
    click_y = pos[1] + 400  # Roughly where text is vertically

    print(f"  Clicking at ({click_x}, {click_y})")

    from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap, CGPointMake

    point = CGPointMake(click_x, click_y)

    # Double-click to select text and open edit dialog
    for _ in range(2):
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.05)
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.15)

    return True


def is_edit_dialog_open():
    """Check if edit dialog is visible (has text fields and Save/Cancel buttons)."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Check for text areas (the edit field)
            if (count of text areas of window 1) > 0 then
                return "dialog_open"
            end if
            -- Also check for Save button as indicator
            set allButtons to every button of window 1
            repeat with btn in allButtons
                try
                    if (name of btn) is "Save" then
                        return "dialog_open"
                    end if
                end try
            end repeat
        on error
            return "error"
        end try
    end tell
end tell
return "no_dialog"
'''
    result = interactions.run_applescript(script)
    return 'dialog_open' in result


def get_edit_text():
    """Get text from edit field."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            if (count of text areas of window 1) > 0 then
                return value of text area 1 of window 1
            end if
        on error errMsg
            return "ERROR:" & errMsg
        end try
    end tell
end tell
return ""
'''
    return interactions.run_applescript(script).strip()


def set_edit_text(text):
    """Set edit text by selecting all and typing."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.2)

    # Select all (Cmd+A)
    interactions.press_key('a', modifiers=['command'], app_name=APP_NAME)
    time.sleep(0.1)

    # Type new text
    script = f'''
tell application "System Events"
    keystroke "{text}"
end tell
'''
    interactions.run_applescript(script)
    time.sleep(0.3)


def toggle_preview():
    """Click the Preview checkbox."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Find checkbox in window
            set allCheckboxes to every checkbox of window 1
            if (count of allCheckboxes) > 0 then
                click item 1 of allCheckboxes
                return "clicked"
            end if
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
end tell
return "not_found"
'''
    result = interactions.run_applescript(script)
    return 'clicked' in result


def main():
    print("=" * 70)
    print("AUTOMATED PREVIEW BUG FIX TEST")
    print("=" * 70)
    print()
    print("Testing that edited text is NOT overwritten when toggling Preview ON")
    print()

    pdf_path = tempfile.mktemp(suffix='.pdf', prefix='preview_test_')
    app_proc = None

    try:
        # Step 1: Create test PDF
        print("[1/7] Creating test PDF...")
        if not create_test_pdf(pdf_path):
            print("  ❌ Failed to create PDF")
            return False
        print(f"  ✓ Created: {os.path.basename(pdf_path)}")

        # Step 2: Launch app with test PDF
        print("[2/7] Launching app with test PDF...")
        app_proc = launch_app_with_test_pdf(pdf_path)
        capture_screenshot("01_launched")

        if not verify_pdf_loaded():
            print("  ❌ PDF did not load")
            return False
        print("  ✓ App launched and PDF loaded")

        # Step 3: Click on text to open edit dialog
        print("[3/7] Opening edit dialog (clicking on PDF text)...")

        dialog_opened = False
        for attempt in range(5):
            click_on_pdf_text()
            time.sleep(1.5)

            if is_edit_dialog_open():
                dialog_opened = True
                break
            print(f"  Attempt {attempt + 1}: Dialog not detected, retrying...")

        capture_screenshot("02_after_click")

        if not dialog_opened:
            print("  ⚠️ Could not confirm dialog opened - continuing anyway")
        else:
            print("  ✓ Edit dialog opened")

        # Step 4: Read original text and modify
        print("[4/7] Modifying text...")
        original_text = get_edit_text()
        print(f"  Original: '{original_text[:40]}...'" if len(original_text) > 40 else f"  Original: '{original_text}'")

        set_edit_text(MODIFIED_TEXT)
        time.sleep(0.5)

        after_edit = get_edit_text()
        print(f"  After edit: '{after_edit}'")
        capture_screenshot("03_after_edit")

        if MODIFIED_TEXT not in after_edit:
            print("  ⚠️ Text may not have been set correctly")

        # Step 5: Toggle Preview ON
        print("[5/7] Toggling Preview ON...")
        if toggle_preview():
            print("  ✓ Preview toggled")
        else:
            print("  ⚠️ Could not confirm toggle")

        capture_screenshot("04_preview_toggled")

        # Step 6: Wait for preview to process
        print("[6/7] Waiting for preview to stabilize (3 seconds)...")
        time.sleep(3)
        capture_screenshot("05_after_wait")

        # Step 7: CRITICAL CHECK - Verify text is preserved
        print("[7/7] Verifying text was preserved...")
        final_text = get_edit_text()
        print(f"  Final text: '{final_text}'")
        capture_screenshot("06_final")

        # Results
        print()
        print("=" * 70)
        print("TEST RESULTS")
        print("=" * 70)

        if MODIFIED_TEXT in final_text:
            print()
            print("  ✅ PASS: Text was PRESERVED after preview toggle!")
            print(f"     Expected: '{MODIFIED_TEXT}'")
            print(f"     Got:      '{final_text}'")
            print()
            print("  The preview bug fix is WORKING correctly.")
            print()
            return True

        if not final_text:
            print()
            print("  ⚠️ INCONCLUSIVE: Could not read text field")
            print("     Accessibility may be limited.")
            print("     Check screenshots in test_output/ for manual verification.")
            return None

        if ORIGINAL_TEXT in final_text or final_text != after_edit:
            print()
            print("  ❌ FAIL: Text was REVERTED after preview toggle!")
            print(f"     Expected: '{MODIFIED_TEXT}'")
            print(f"     Got:      '{final_text}'")
            print()
            print("  The preview bug fix is NOT working - text was overwritten.")
            return False

        print()
        print(f"  ❓ UNEXPECTED: Text is '{final_text}'")
        return None

    finally:
        print()
        print("Cleaning up...")

        # Terminate app
        if app_proc:
            app_proc.terminate()
            try:
                app_proc.wait(timeout=3)
            except:
                app_proc.kill()

        subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)

        # Remove test PDF
        try:
            os.remove(pdf_path)
        except:
            pass

        print("Done.")


if __name__ == "__main__":
    result = main()
    if result is True:
        sys.exit(0)
    elif result is False:
        sys.exit(1)
    else:
        sys.exit(2)  # Inconclusive
