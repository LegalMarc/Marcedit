#!/usr/bin/env python3
"""
Robust automated test for preview bug fix using direct file opening.
"""

import sys
import time
import os
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import interactions

APP_NAME = "Marcedit"
APP_PATH = "/Users/mhm/Documents/Dev/Marcedit/.build/release/Marcedit"
MODIFIED_TEXT = "PREVIEW_TEST_12345"


def create_test_pdf(path):
    """Create a simple test PDF with known text."""
    script = f'''
import fitz
doc = fitz.open()
page = doc.new_page()
# Add text in the center of the page for easier clicking
page.insert_text((200, 400), "Hello World Test", fontsize=14, fontname="helv")
page.insert_text((200, 430), "Second Line Here", fontsize=14, fontname="helv")
doc.save("{path}")
doc.close()
print("created")
'''
    result = subprocess.run(['python3', '-c', script], capture_output=True, text=True)
    return 'created' in result.stdout


def capture_screenshot(name):
    """Capture a screenshot for debugging."""
    output_dir = os.path.join(os.path.dirname(__file__), "test_output")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"robust_{name}.png")
    subprocess.run(['screencapture', '-x', filepath], capture_output=True)
    print(f"  Screenshot: {filepath}")
    return filepath


def launch_app():
    """Launch Marcedit."""
    subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
    time.sleep(0.5)

    subprocess.Popen([APP_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(10):
        time.sleep(1)
        result = interactions.run_applescript('tell application "System Events" to return name of every process')
        if APP_NAME in result:
            print("  ✓ App launched")
            return True
    return False


def open_pdf_via_menu(pdf_path):
    """Open PDF using File > Open menu."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.5)

    # Use keyboard shortcut Cmd+O
    interactions.press_key('o', modifiers=['command'], app_name=APP_NAME)
    time.sleep(1)

    # Type the path in the open dialog
    script = f'''
tell application "System Events"
    tell process "Marcedit"
        -- Wait for open dialog
        repeat 10 times
            try
                if (exists sheet 1 of window 1) then
                    exit repeat
                end if
            end try
            delay 0.5
        end repeat

        -- Use Cmd+Shift+G to go to path
        keystroke "g" using {{command down, shift down}}
        delay 0.5

        -- Type the path
        keystroke "{pdf_path}"
        delay 0.3

        -- Press Enter to go to path
        keystroke return
        delay 0.5

        -- Press Enter to open file
        keystroke return
        delay 0.3

        return "opened"
    end tell
end tell
'''
    result = interactions.run_applescript(script)
    time.sleep(2)  # Wait for PDF to load
    return 'opened' in result


def open_pdf_via_drag_drop(pdf_path):
    """Alternative: Open PDF by opening it directly with the app."""
    script = f'''
tell application "Marcedit"
    activate
    open POSIX file "{pdf_path}"
end tell
delay 2
return "opened"
'''
    result = interactions.run_applescript(script)
    return 'opened' in result


def verify_pdf_loaded():
    """Check if PDF is displayed."""
    time.sleep(1)
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            set winContent to entire contents of window 1
            repeat with elem in winContent
                try
                    set elemDesc to description of elem
                    if elemDesc contains "PDF" then
                        return "pdf_found"
                    end if
                end try
            end repeat
            -- Check if "No Document Selected" is NOT visible
            set allStaticTexts to every static text of window 1
            repeat with txt in allStaticTexts
                if (value of txt) contains "No Document" then
                    return "no_document"
                end if
            end repeat
            return "maybe_loaded"
        end try
    end tell
end tell
return "unknown"
'''
    result = interactions.run_applescript(script)
    return 'no_document' not in result


def click_on_pdf_text():
    """Click directly on PDF content area using CGEvent."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.3)

    # Get window position and size
    pos = interactions.get_window_position(APP_NAME)
    size = interactions.get_window_size(APP_NAME)

    if not pos or not size:
        print("  Could not get window position")
        return False

    # Calculate click position - center-right of window (PDF content area)
    # The sidebar is about 240px, so click to the right of that
    click_x = pos[0] + 500  # Well into the PDF area
    click_y = pos[1] + 400  # Middle height

    print(f"  Window at: {pos}, size: {size}")
    print(f"  Clicking at: ({click_x}, {click_y})")

    # Double-click using cliclick or CGEvent
    # First try using Python's Quartz framework directly
    try:
        from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap, CGPointMake

        point = CGPointMake(click_x, click_y)

        # First click
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.05)
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.1)

        # Second click (double-click)
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.05)
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
        CGEventPost(kCGHIDEventTap, event)

        print("  ✓ Double-clicked via CGEvent")
        return True
    except Exception as e:
        print(f"  CGEvent failed: {e}")

    # Fallback to AppleScript
    script = f'''
tell application "System Events"
    click at {{{click_x}, {click_y}}}
    delay 0.1
    click at {{{click_x}, {click_y}}}
end tell
return "clicked"
'''
    interactions.run_applescript(script)
    print("  ✓ Double-clicked via AppleScript")
    return True


def check_edit_dialog_open():
    """Check if edit dialog is open."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Look for text field, text area, or any edit-like element
            set fieldCount to count of text fields of window 1
            set areaCount to count of text areas of window 1
            if fieldCount > 0 or areaCount > 0 then
                return "dialog_open"
            end if

            -- Also check for buttons like "Save" or "Cancel" that indicate dialog
            set allButtons to every button of window 1
            repeat with btn in allButtons
                set btnName to name of btn
                if btnName is "Save" or btnName is "Cancel" then
                    return "dialog_open"
                end if
            end repeat
        end try
    end tell
end tell
return "no_dialog"
'''
    result = interactions.run_applescript(script)
    return 'dialog_open' in result


def get_text_field_value():
    """Get value from text field or text area."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            if (count of text areas of window 1) > 0 then
                return value of text area 1 of window 1
            end if
            if (count of text fields of window 1) > 0 then
                return value of text field 1 of window 1
            end if
        end try
    end tell
end tell
return ""
'''
    return interactions.run_applescript(script).strip()


def set_text_field_value(text):
    """Set text field value by selecting all and typing."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.2)

    # Select all
    interactions.press_key('a', modifiers=['command'], app_name=APP_NAME)
    time.sleep(0.1)

    # Type new text
    script = f'''
tell application "System Events"
    tell process "Marcedit"
        keystroke "{text}"
    end tell
end tell
'''
    interactions.run_applescript(script)
    time.sleep(0.3)


def toggle_preview():
    """Toggle the Preview checkbox."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Find and click Preview checkbox
            set allCheckboxes to every checkbox of window 1
            repeat with cb in allCheckboxes
                try
                    set cbTitle to title of cb
                    if cbTitle contains "Preview" then
                        click cb
                        return "clicked_preview"
                    end if
                end try
                try
                    set cbName to name of cb
                    if cbName contains "Preview" then
                        click cb
                        return "clicked_preview"
                    end if
                end try
            end repeat

            -- Try accessibility identifier
            click (first checkbox whose value of attribute "AXIdentifier" is "PreviewToggle") of window 1
            return "clicked_by_id"
        on error
            -- Try clicking any checkbox
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


def main():
    print("=" * 70)
    print("ROBUST PREVIEW BUG FIX TEST")
    print("=" * 70)
    print()

    # Create test PDF
    pdf_path = tempfile.mktemp(suffix='.pdf', prefix='marcedit_test_')

    try:
        print("[1/8] Creating test PDF...")
        if not create_test_pdf(pdf_path):
            print("  ❌ Failed to create PDF")
            return False
        print(f"  ✓ Created: {pdf_path}")

        print("[2/8] Launching Marcedit...")
        if not launch_app():
            print("  ❌ Failed to launch app")
            return False

        time.sleep(2)
        capture_screenshot("01_launched")

        print("[3/8] Opening PDF file...")
        # Try direct open first
        if not open_pdf_via_drag_drop(pdf_path):
            print("  Trying menu open...")
            if not open_pdf_via_menu(pdf_path):
                print("  ❌ Failed to open PDF")
                return False

        time.sleep(2)
        capture_screenshot("02_pdf_opened")

        print("[4/8] Verifying PDF loaded...")
        if verify_pdf_loaded():
            print("  ✓ PDF appears to be loaded")
        else:
            print("  ⚠ Could not confirm PDF loaded")

        print("[5/8] Double-clicking on text to open edit dialog...")
        click_on_pdf_text()
        time.sleep(2)
        capture_screenshot("03_after_click")

        # Check if dialog opened
        dialog_opened = False
        for attempt in range(3):
            if check_edit_dialog_open():
                dialog_opened = True
                break
            print(f"  Attempt {attempt + 1}: Dialog not detected, trying again...")
            click_on_pdf_text()
            time.sleep(2)

        capture_screenshot("04_dialog_check")

        if not dialog_opened:
            print("  ⚠ Edit dialog may not have opened")
            print("  Checking text fields anyway...")
        else:
            print("  ✓ Edit dialog opened")

        print("[6/8] Getting original text and modifying...")
        original_text = get_text_field_value()
        print(f"  Original: '{original_text[:50]}...'" if len(original_text) > 50 else f"  Original: '{original_text}'")

        set_text_field_value(MODIFIED_TEXT)
        time.sleep(0.5)

        text_after_edit = get_text_field_value()
        print(f"  After edit: '{text_after_edit}'")
        capture_screenshot("05_after_edit")

        print("[7/8] Toggling Preview ON...")
        if toggle_preview():
            print("  ✓ Preview toggled")
        else:
            print("  ⚠ Could not confirm toggle")

        # Wait for preview to render and any state changes
        print("  Waiting 3 seconds for preview to stabilize...")
        time.sleep(3)
        capture_screenshot("06_after_preview")

        print("[8/8] Verifying text preserved after preview...")
        text_after_preview = get_text_field_value()
        print(f"  Text after preview: '{text_after_preview}'")
        capture_screenshot("07_final")

        print()
        print("=" * 70)
        print("TEST RESULTS")
        print("=" * 70)

        if MODIFIED_TEXT in text_after_preview:
            print()
            print("  ✅ PASS: Text preserved after preview toggle!")
            print(f"     Expected: '{MODIFIED_TEXT}'")
            print(f"     Got:      '{text_after_preview}'")
            return True
        elif not text_after_preview:
            print()
            print("  ⚠ INCONCLUSIVE: Could not read text field")
            print("     This may be due to accessibility limitations.")
            print("     Check screenshots in test_output/ for manual verification.")
            return False
        else:
            print()
            print("  ❌ FAIL: Text changed unexpectedly!")
            print(f"     Expected: '{MODIFIED_TEXT}'")
            print(f"     Got:      '{text_after_preview}'")
            return False

    finally:
        print()
        print("Cleaning up...")
        subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        print("Done.")


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
