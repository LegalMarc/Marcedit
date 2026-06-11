#!/usr/bin/env python3
"""
Automated test for preview bug fix using coordinate-based clicking.
"""

import sys
import time
import os
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import interactions

APP_PATH = "/Users/mhm/Documents/Dev/Marcedit/.build/Marcedit.app/Contents/MacOS/Marcedit"
APP_NAME = "Marcedit"
ORIGINAL_TEXT = "CLICK_HERE_TO_EDIT"
MODIFIED_TEXT = "MODIFIED_BY_TEST"


def create_test_pdf(path):
    """Create test PDF with known text."""
    script = f'''
import fitz
doc = fitz.open()
page = doc.new_page(width=612, height=792)
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
    filepath = os.path.join(output_dir, f"hooks_{name}.png")
    subprocess.run(['screencapture', '-x', filepath], capture_output=True)
    return filepath


def launch_app_with_test_pdf(pdf_path, auto_edit=False, test_text=None):
    """Launch app with test mode and PDF path."""
    subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
    time.sleep(1)

    args = [APP_PATH, '--run-ui-tests', f'--test-pdf-path={pdf_path}']
    if auto_edit:
        args.append('--auto-edit')
    if test_text:
        args.append(f'--test-text={test_text}')

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    for _ in range(10):
        time.sleep(1)
        procs = interactions.run_applescript('tell application "System Events" to return name of every process')
        if APP_NAME in procs:
            break

    # Extra time for PDF to load and auto-edit to trigger
    time.sleep(4 if auto_edit else 3)
    return proc


def perform_double_click(x, y):
    """Perform double-click at coordinates."""
    from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap, CGPointMake

    point = CGPointMake(float(x), float(y))

    for _ in range(2):
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.05)
        event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.15)


def has_edit_dialog():
    """Check if edit dialog is open by searching entire contents for text area."""
    script = f'''
tell application "System Events"
    tell process "{APP_NAME}"
        try
            set allElems to entire contents of window 1
            repeat with elem in allElems
                try
                    if class of elem is text area then
                        return "open"
                    end if
                end try
            end repeat
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
end tell
return "closed"
'''
    result = interactions.run_applescript(script)
    return "open" in result


def get_text_field_value():
    """Get value from text area by searching entire contents."""
    script = f'''
tell application "System Events"
    tell process "{APP_NAME}"
        try
            set allElems to entire contents of window 1
            repeat with elem in allElems
                try
                    if class of elem is text area then
                        return value of elem
                    end if
                end try
            end repeat
        on error errMsg
            return "ERROR:" & errMsg
        end try
    end tell
end tell
return ""
'''
    return interactions.run_applescript(script).strip()


def set_text_field_value(text):
    """Set value directly via accessibility API."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.2)

    # Try to set value directly
    text_escaped = text.replace('\\', '\\\\').replace('"', '\\"')
    script = f'''
tell application "System Events"
    tell process "{APP_NAME}"
        try
            set allElems to entire contents of window 1
            repeat with elem in allElems
                try
                    if class of elem is text area then
                        set value of elem to "{text_escaped}"
                        return "set"
                    end if
                end try
            end repeat
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
end tell
return "not_found"
'''
    result = interactions.run_applescript(script)
    print(f"    set_text_field_value result: {result}")

    # If direct set didn't work, try click + keystrokes
    if "set" not in result:
        # Click on text area to focus
        click_script = f'''
tell application "System Events"
    tell process "{APP_NAME}"
        try
            set allElems to entire contents of window 1
            repeat with elem in allElems
                try
                    if class of elem is text area then
                        click elem
                        return "clicked"
                    end if
                end try
            end repeat
        end try
    end tell
end tell
return "not_found"
'''
        interactions.run_applescript(click_script)
        time.sleep(0.2)

        # Select all with Cmd+A
        interactions.press_key('a', modifiers=['command'], app_name=APP_NAME)
        time.sleep(0.1)

        # Type the new text
        keystroke_script = f'''
tell application "System Events"
    keystroke "{text_escaped}"
end tell
'''
        interactions.run_applescript(keystroke_script)

    time.sleep(0.3)


def click_preview_checkbox():
    """Click the Preview checkbox by searching entire contents."""
    script = f'''
tell application "System Events"
    tell process "{APP_NAME}"
        try
            set allElems to entire contents of window 1
            repeat with elem in allElems
                try
                    if class of elem is checkbox then
                        click elem
                        return "clicked"
                    end if
                end try
            end repeat
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
end tell
return "not_found"
'''
    result = interactions.run_applescript(script)
    return "clicked" in result


def main():
    print("=" * 70)
    print("PREVIEW BUG FIX TEST")
    print("=" * 70)
    print()

    pdf_path = tempfile.mktemp(suffix='.pdf', prefix='preview_test_')
    app_proc = None

    try:
        # Step 1: Create test PDF
        print("[1/8] Creating test PDF...")
        if not create_test_pdf(pdf_path):
            print("  FAIL: Could not create test PDF")
            return False
        print(f"  OK: Created PDF")

        # Step 2: Launch app with auto-edit enabled
        print("[2/8] Launching app with --auto-edit...")
        app_proc = launch_app_with_test_pdf(pdf_path, auto_edit=True, test_text=ORIGINAL_TEXT)
        interactions.activate_app(APP_NAME)
        time.sleep(1)
        capture_screenshot("01_launched")
        print("  OK: App launched")

        # Step 3: Wait for edit dialog to auto-open
        print("[3/8] Waiting for edit dialog to auto-open...")
        interactions.activate_app(APP_NAME)

        dialog_opened = False
        for attempt in range(10):
            time.sleep(1)
            if has_edit_dialog():
                dialog_opened = True
                print(f"  OK: Edit dialog opened (after {attempt + 1}s)")
                break
            print(f"  Waiting... ({attempt + 1}s)")

        capture_screenshot("02_dialog_opened")

        if not dialog_opened:
            print("  WARNING: Dialog did not auto-open")

        # Step 4: Read current text
        print("[4/8] Reading current text...")
        current_text = get_text_field_value()
        print(f"  Text: '{current_text}'")

        if not current_text:
            print("  WARNING: No text found - dialog may not be open")
            capture_screenshot("02b_no_text")
            # Continue anyway to see what happens

        # Step 5: Modify text
        print("[5/8] Modifying text...")
        set_text_field_value(MODIFIED_TEXT)
        time.sleep(0.5)

        after_edit = get_text_field_value()
        print(f"  Text after edit: '{after_edit}'")
        capture_screenshot("03_after_edit")

        # Step 6: Toggle Preview
        print("[6/8] Toggling Preview...")
        if click_preview_checkbox():
            print("  OK: Clicked Preview checkbox")
        else:
            print("  WARNING: Could not click Preview checkbox")

        capture_screenshot("04_preview_toggled")

        # Step 7: Wait
        print("[7/8] Waiting for preview (3 seconds)...")
        time.sleep(3)
        capture_screenshot("05_after_wait")

        # Step 8: Verify
        print("[8/8] Verifying text preservation...")
        final_text = get_text_field_value()
        print(f"  Final text: '{final_text}'")
        capture_screenshot("06_final")

        # Results
        print()
        print("=" * 70)
        print("TEST RESULTS")
        print("=" * 70)

        if MODIFIED_TEXT in final_text:
            print()
            print("  PASS: Text was PRESERVED after preview toggle!")
            print(f"  Expected: '{MODIFIED_TEXT}'")
            print(f"  Got:      '{final_text}'")
            print()
            return True

        if not final_text:
            print()
            print("  INCONCLUSIVE: Could not read text field")
            return None

        if ORIGINAL_TEXT in final_text:
            print()
            print("  FAIL: Text was REVERTED!")
            print(f"  Expected: '{MODIFIED_TEXT}'")
            print(f"  Got:      '{final_text}'")
            return False

        print()
        print(f"  UNEXPECTED: '{final_text}'")
        return None

    finally:
        print()
        print("Cleaning up...")

        if app_proc:
            app_proc.terminate()
            try:
                app_proc.wait(timeout=3)
            except:
                app_proc.kill()

        subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)

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
        sys.exit(2)
