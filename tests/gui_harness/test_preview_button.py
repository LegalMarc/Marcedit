#!/usr/bin/env python3
"""
Test preview functionality by clicking UI buttons directly.
"""

import sys
import time
import os
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import interactions

APP_NAME = "Marcedit"
APP_PATH = ".build/release/Marcedit"
MODIFIED_TEXT = "PREVIEW_TEST_12345"


def create_test_pdf(path):
    """Create test PDF."""
    script = f'''
import fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text((200, 400), "Hello World Test", fontsize=14, fontname="helv")
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
    filepath = os.path.join(output_dir, f"btn_{name}.png")
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
            return True
    return False


def click_open_button_and_select_file(pdf_path):
    """Click 'Open PDF File' button and select file."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.5)

    # Click the "Open PDF File" button
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Find and click the "Open PDF File" button
            click button "Open PDF File" of window 1
            return "clicked"
        on error
            -- Try by accessibility
            set allButtons to every button of window 1
            repeat with btn in allButtons
                try
                    if (title of btn) contains "Open" then
                        click btn
                        return "clicked"
                    end if
                end try
            end repeat
        end try
    end tell
end tell
return "not_found"
'''
    result = interactions.run_applescript(script)
    print(f"  Open button: {result}")
    time.sleep(1)

    # Now navigate to the file in the open dialog
    script = f'''
tell application "System Events"
    tell process "Marcedit"
        -- Wait for open dialog
        delay 1

        -- Use Cmd+Shift+G to go to folder
        keystroke "g" using {{command down, shift down}}
        delay 0.5

        -- Get the directory path
        set dirPath to "{os.path.dirname(pdf_path)}"
        keystroke dirPath
        delay 0.2
        keystroke return
        delay 1

        -- Now we should be in the folder, type filename
        set fileName to "{os.path.basename(pdf_path)}"
        keystroke fileName
        delay 0.2
        keystroke return
        delay 1

        return "opened"
    end tell
end tell
'''
    result = interactions.run_applescript(script)
    print(f"  File selection: {result}")
    time.sleep(2)
    return 'opened' in result


def verify_pdf_loaded():
    """Check if PDF loaded."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Check sidebar for document entry
            set allStaticTexts to every static text of window 1
            repeat with txt in allStaticTexts
                try
                    if (value of txt) contains "No Document" then
                        return "no_doc"
                    end if
                end try
            end repeat
            -- Check if there's a PDF-related element
            set winContent to entire contents of window 1
            return "maybe_loaded"
        end try
    end tell
end tell
return "unknown"
'''
    result = interactions.run_applescript(script)
    return 'no_doc' not in result


def find_text_on_pdf_and_click():
    """Try to find text position on PDF and click it."""
    # Get window bounds
    pos = interactions.get_window_position(APP_NAME)
    size = interactions.get_window_size(APP_NAME)

    if not pos or not size:
        return False

    # The sidebar is ~240px wide. PDF content starts after that.
    # The text "Hello World Test" was placed at (200, 400) in PDF coords
    # which translates to roughly center-top of the visible PDF area

    # Try clicking at different positions in the PDF area
    pdf_start_x = pos[0] + 280  # After sidebar
    pdf_center_y = pos[1] + 400  # Middle area

    from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap, CGPointMake

    # Try a grid of positions
    positions = [
        (pdf_start_x + 100, pos[1] + 200),  # Upper area
        (pdf_start_x + 200, pos[1] + 300),
        (pdf_start_x + 150, pos[1] + 400),
        (pdf_start_x + 200, pos[1] + 350),
    ]

    for x, y in positions:
        point = CGPointMake(x, y)
        print(f"  Trying click at ({x}, {y})...")

        # Double-click
        for _ in range(2):
            event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
            CGEventPost(kCGHIDEventTap, event)
            time.sleep(0.05)
            event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
            CGEventPost(kCGHIDEventTap, event)
            time.sleep(0.1)

        time.sleep(1)

        # Check if dialog opened
        if check_edit_dialog():
            print(f"  ✓ Dialog opened at ({x}, {y})")
            return True

    return False


def check_edit_dialog():
    """Check if edit dialog is open."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            set fieldCount to count of text fields of window 1
            set areaCount to count of text areas of window 1
            if fieldCount > 0 or areaCount > 0 then
                return "has_fields"
            end if
            -- Check for Save/Cancel buttons
            set allButtons to every button of window 1
            repeat with btn in allButtons
                try
                    set btnName to name of btn
                    if btnName is "Save" then
                        return "has_save"
                    end if
                end try
            end repeat
        end try
    end tell
end tell
return "no_dialog"
'''
    result = interactions.run_applescript(script)
    return 'has_' in result


def get_text_value():
    """Get text from field or area."""
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


def set_text_value(text):
    """Set text value."""
    interactions.press_key('a', modifiers=['command'], app_name=APP_NAME)
    time.sleep(0.1)
    script = f'''
tell application "System Events"
    keystroke "{text}"
end tell
'''
    interactions.run_applescript(script)
    time.sleep(0.3)


def click_preview_toggle():
    """Click Preview toggle."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            set allCheckboxes to every checkbox of window 1
            repeat with cb in allCheckboxes
                try
                    click cb
                    return "clicked"
                end try
            end repeat
        end try
    end tell
end tell
return "not_found"
'''
    result = interactions.run_applescript(script)
    return 'clicked' in result


def main():
    print("=" * 70)
    print("PREVIEW TEST - BUTTON APPROACH")
    print("=" * 70)
    print()

    pdf_path = tempfile.mktemp(suffix='.pdf', prefix='test_')

    try:
        print("[1] Creating test PDF...")
        if not create_test_pdf(pdf_path):
            print("  ❌ Failed")
            return False
        print(f"  ✓ {pdf_path}")

        print("[2] Launching app...")
        if not launch_app():
            print("  ❌ Failed")
            return False
        print("  ✓ Launched")
        time.sleep(2)
        capture_screenshot("01_launched")

        print("[3] Opening PDF via button...")
        click_open_button_and_select_file(pdf_path)
        time.sleep(2)
        capture_screenshot("02_opened")

        print("[4] Checking PDF loaded...")
        if verify_pdf_loaded():
            print("  ✓ PDF loaded")
        else:
            print("  ⚠ May not have loaded")
            # Try listing sidebar items
            script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            return (entire contents of window 1) as string
        end try
    end tell
end tell
'''
            # interactions.run_applescript(script)  # Too verbose

        print("[5] Clicking on PDF text...")
        if find_text_on_pdf_and_click():
            print("  ✓ Edit dialog opened")
        else:
            print("  ⚠ Could not open dialog")

        capture_screenshot("03_after_clicks")

        print("[6] Getting/setting text...")
        orig = get_text_value()
        print(f"  Original: '{orig[:30]}...'" if len(orig) > 30 else f"  Original: '{orig}'")

        set_text_value(MODIFIED_TEXT)
        after_edit = get_text_value()
        print(f"  After edit: '{after_edit}'")
        capture_screenshot("04_after_edit")

        print("[7] Toggling Preview...")
        if click_preview_toggle():
            print("  ✓ Toggled")
        else:
            print("  ⚠ Could not toggle")

        time.sleep(3)
        capture_screenshot("05_after_preview")

        print("[8] Final verification...")
        final = get_text_value()
        print(f"  Final: '{final}'")
        capture_screenshot("06_final")

        print()
        print("=" * 70)
        if MODIFIED_TEXT in final:
            print("  ✅ PASS: Text preserved!")
            return True
        elif not final:
            print("  ⚠ INCONCLUSIVE: Could not read text")
            return False
        else:
            print(f"  ❌ FAIL: Expected '{MODIFIED_TEXT}', got '{final}'")
            return False

    finally:
        print()
        print("Cleanup...")
        subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
