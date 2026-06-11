#!/usr/bin/env python3
"""
Final preview test using macOS open command for file opening.
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
MODIFIED_TEXT = "TESTPREVIEW123"


def create_test_pdf(path):
    """Create test PDF with text in visible area."""
    script = f'''
import fitz
doc = fitz.open()
page = doc.new_page(width=612, height=792)  # US Letter
# Place text where it will be visible (center-ish area)
page.insert_text((100, 200), "ORIGINAL_TEXT_HERE", fontsize=18, fontname="helv")
page.insert_text((100, 250), "Second line of text", fontsize=14, fontname="helv")
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
    filepath = os.path.join(output_dir, f"final_{name}.png")
    subprocess.run(['screencapture', '-x', filepath], capture_output=True)
    return filepath


def kill_app():
    subprocess.run(['pkill', '-x', 'Marcedit'], capture_output=True)
    time.sleep(0.5)


def open_pdf_with_app(pdf_path):
    """Use macOS open command to open PDF with app."""
    # First, kill any existing instance
    kill_app()
    time.sleep(0.5)

    # Use 'open -a' to open the file with the specific app
    result = subprocess.run(
        ['open', '-a', APP_PATH, pdf_path],
        capture_output=True, text=True
    )

    # Wait for app to launch and file to load
    for _ in range(15):
        time.sleep(1)
        procs = interactions.run_applescript('tell application "System Events" to return name of every process')
        if APP_NAME in procs:
            break

    time.sleep(2)  # Extra time for PDF to render
    return APP_NAME in procs


def is_pdf_loaded():
    """Check if PDF is displayed (not showing 'No Document')."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            set allTexts to every static text of window 1
            repeat with txt in allTexts
                try
                    if (value of txt) contains "No Document" then
                        return "empty"
                    end if
                end try
            end repeat
        end try
    end tell
end tell
return "loaded"
'''
    result = interactions.run_applescript(script)
    return 'loaded' in result


def click_on_pdf(x_offset=400, y_offset=300):
    """Click on PDF using CGEvent."""
    interactions.activate_app(APP_NAME)
    time.sleep(0.3)

    pos = interactions.get_window_position(APP_NAME)
    if not pos:
        return False

    # Calculate absolute position
    click_x = pos[0] + x_offset
    click_y = pos[1] + y_offset

    try:
        from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap, CGPointMake

        point = CGPointMake(click_x, click_y)

        # Double-click
        for _ in range(2):
            event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
            CGEventPost(kCGHIDEventTap, event)
            time.sleep(0.05)
            event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
            CGEventPost(kCGHIDEventTap, event)
            time.sleep(0.1)

        return True
    except Exception as e:
        print(f"  Click error: {e}")
        return False


def is_edit_dialog_open():
    """Check for edit dialog."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Check for text fields/areas
            if (count of text fields of window 1) > 0 then return "yes"
            if (count of text areas of window 1) > 0 then return "yes"

            -- Check for Cancel/Save buttons (dialog indicators)
            set allButtons to every button of window 1
            repeat with btn in allButtons
                try
                    if (name of btn) is "Cancel" then return "yes"
                    if (name of btn) is "Save" then return "yes"
                end try
            end repeat
        end try
    end tell
end tell
return "no"
'''
    result = interactions.run_applescript(script)
    return 'yes' in result


def get_text_field_content():
    """Get text from edit field."""
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


def type_text(text):
    """Type text using System Events."""
    interactions.activate_app(APP_NAME)
    # Select all first
    interactions.press_key('a', modifiers=['command'], app_name=APP_NAME)
    time.sleep(0.1)
    # Type
    script = f'''
tell application "System Events"
    keystroke "{text}"
end tell
'''
    interactions.run_applescript(script)
    time.sleep(0.3)


def click_preview_checkbox():
    """Click the Preview checkbox."""
    script = '''
tell application "System Events"
    tell process "Marcedit"
        try
            -- Look for checkbox
            set allCB to every checkbox of window 1
            if (count of allCB) > 0 then
                click item 1 of allCB
                return "clicked"
            end if
        end try
    end tell
end tell
return "not_found"
'''
    result = interactions.run_applescript(script)
    return 'clicked' in result


def main():
    print("=" * 60)
    print("PREVIEW BUG FIX - FINAL TEST")
    print("=" * 60)
    print()

    # Create temp PDF
    pdf_path = tempfile.mktemp(suffix='.pdf', prefix='marcedit_test_')

    try:
        # Step 1: Create PDF
        print("[1] Creating test PDF...")
        if not create_test_pdf(pdf_path):
            print("  ❌ Failed to create PDF")
            return False
        print(f"  ✓ Created: {os.path.basename(pdf_path)}")

        # Step 2: Open with app
        print("[2] Opening PDF with Marcedit...")
        if not open_pdf_with_app(pdf_path):
            print("  ❌ Failed to open")
            return False
        print("  ✓ App launched with PDF")
        capture_screenshot("01_opened")

        # Step 3: Verify PDF loaded
        print("[3] Verifying PDF loaded...")
        time.sleep(2)
        if is_pdf_loaded():
            print("  ✓ PDF is loaded")
        else:
            print("  ⚠ PDF may not have loaded")
        capture_screenshot("02_pdf_state")

        # Step 4: Try to open edit dialog by clicking in PDF area
        print("[4] Opening edit dialog (clicking on PDF)...")

        # The sidebar is ~240px wide. PDF area starts after that.
        # Our text is at (100, 200) in PDF coords
        # Window title bar is ~40px, so y_offset needs adjustment

        # Try several positions in the PDF content area
        positions = [
            (450, 250),   # Upper area
            (500, 300),   # Mid area
            (450, 350),   # Lower-mid
            (550, 280),   # Right of center
        ]

        dialog_opened = False
        for i, (x_off, y_off) in enumerate(positions):
            print(f"  Attempt {i+1}: clicking at offset ({x_off}, {y_off})...")
            click_on_pdf(x_off, y_off)
            time.sleep(1.5)

            if is_edit_dialog_open():
                print(f"  ✓ Dialog opened!")
                dialog_opened = True
                break

        capture_screenshot("03_after_clicks")

        if not dialog_opened:
            print("  ⚠ Could not open edit dialog via clicks")
            print("  Checking current state...")

        # Step 5: Read and modify text
        print("[5] Reading/modifying text...")
        original = get_text_field_content()
        print(f"  Original text: '{original[:40]}'" if len(original) > 40 else f"  Original text: '{original}'")

        type_text(MODIFIED_TEXT)
        after_edit = get_text_field_content()
        print(f"  After typing: '{after_edit}'")
        capture_screenshot("04_after_typing")

        # Step 6: Toggle Preview
        print("[6] Toggling Preview...")
        if click_preview_checkbox():
            print("  ✓ Checkbox clicked")
        else:
            print("  ⚠ Could not find checkbox")
        capture_screenshot("05_preview_toggled")

        # Step 7: Wait and verify
        print("[7] Waiting for preview to stabilize (3s)...")
        time.sleep(3)
        capture_screenshot("06_after_wait")

        # Step 8: Final check
        print("[8] Final verification...")
        final_text = get_text_field_content()
        print(f"  Final text: '{final_text}'")
        capture_screenshot("07_final")

        # Results
        print()
        print("=" * 60)
        print("RESULTS")
        print("=" * 60)

        if not final_text and not original:
            print()
            print("  ⚠ INCONCLUSIVE: Could not access text fields")
            print("     AppleScript/Accessibility limitations prevented reading UI.")
            print("     Screenshots saved for manual verification.")
            print()
            print("     Check: tests/gui_harness/test_output/final_*.png")
            return None  # Inconclusive

        if MODIFIED_TEXT in final_text:
            print()
            print("  ✅ PASS: Text was preserved after Preview toggle!")
            print(f"     The fix is working correctly.")
            return True

        if final_text == original or "ORIGINAL" in final_text:
            print()
            print("  ❌ FAIL: Text reverted to original!")
            print("     The preview bug fix is NOT working.")
            return False

        print()
        print(f"  ❓ UNEXPECTED: '{final_text}'")
        return None

    finally:
        print()
        print("Cleanup...")
        kill_app()
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
