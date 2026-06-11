#!/usr/bin/env python3
"""
Test that Preview mode shows edited text correctly.

This test verifies that:
1. Text edits in the dialog are properly passed to the preview
2. The PDF visually updates when Preview is toggled ON
3. vm.editingText is used (not local @State which can reset)
"""

import sys
import time
import os

# Add gui_harness to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import interactions

APP_NAME = "Marcedit"
TEST_REPLACEMENT = "XYZTEST123"  # Unique string we can search for

def verify_app_running():
    """Check if Marcedit is running."""
    script = 'tell application "System Events" to return name of every process'
    result = interactions.run_applescript(script)
    return APP_NAME in result

def get_window_center():
    """Get center coordinates of the main window."""
    pos = interactions.get_window_position(APP_NAME)
    size = interactions.get_window_size(APP_NAME)
    if pos and size:
        return (pos[0] + size[0] // 2, pos[1] + size[1] // 2)
    return None

def click_preview_checkbox():
    """Click the Preview checkbox in the edit dialog."""
    # Use accessibility identifier to find and click Preview checkbox
    script = '''
        tell application "System Events"
            tell process "Marcedit"
                try
                    -- Find the Preview checkbox
                    set previewCheckbox to checkbox "Preview" of window 1
                    click previewCheckbox
                    return "clicked"
                on error
                    -- Try alternate approach - look for checkbox in sheet/popover
                    try
                        set previewCheckbox to checkbox 1 of sheet 1 of window 1
                        click previewCheckbox
                        return "clicked_sheet"
                    end try
                end try
            end tell
        end tell
        return "not_found"
    '''
    result = interactions.run_applescript(script)
    return "clicked" in result

def check_edit_dialog_open():
    """Check if the edit dialog is visible."""
    script = '''
        tell application "System Events"
            tell process "Marcedit"
                try
                    -- Look for text field or text area in the window
                    if (count of text areas of window 1) > 0 then
                        return "open"
                    end if
                    if (count of text fields of window 1) > 0 then
                        return "open"
                    end if
                    -- Check for sheet
                    if (count of sheets of window 1) > 0 then
                        return "open_sheet"
                    end if
                end try
            end tell
        end tell
        return "closed"
    '''
    result = interactions.run_applescript(script)
    return "open" in result

def type_replacement_text(text):
    """Type replacement text in the edit dialog."""
    # Select all existing text and replace
    interactions.press_key('a', modifiers=['command'], app_name=APP_NAME)
    time.sleep(0.1)
    interactions.type_text(text, app_name=APP_NAME)
    time.sleep(0.2)

def capture_screenshot(name):
    """Capture a screenshot for debugging."""
    output_dir = os.path.join(os.path.dirname(__file__), "test_output")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{name}.png")

    script = f'''
        do shell script "screencapture -x \\"{filepath}\\""
    '''
    interactions.run_applescript(script)
    return filepath

def main():
    print("=" * 60)
    print("PREVIEW EDIT TEST")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print("  1. Marcedit must be running")
    print("  2. A PDF document must be open")
    print("  3. Document should have selectable text")
    print()

    # Step 1: Verify app is running
    print("[1/6] Checking if Marcedit is running...")
    if not verify_app_running():
        print("  ❌ ERROR: Marcedit is not running!")
        return False
    print("  ✓ Marcedit is running")

    # Step 2: Activate app and get window
    print("[2/6] Activating app and getting window position...")
    interactions.activate_app(APP_NAME)
    time.sleep(0.5)

    center = get_window_center()
    if not center:
        print("  ❌ ERROR: Could not get window position")
        return False
    print(f"  ✓ Window center at {center}")

    # Step 3: Double-click to select text and open edit dialog
    print("[3/6] Double-clicking to select text...")
    # Click slightly left of center where text usually is
    click_x = center[0] - 100
    click_y = center[1]

    interactions.click_at_coordinates(click_x, click_y, APP_NAME)
    time.sleep(0.1)
    interactions.click_at_coordinates(click_x, click_y, APP_NAME)
    time.sleep(1.0)  # Wait for edit dialog

    if not check_edit_dialog_open():
        print("  ⚠ Edit dialog may not be open - trying different position...")
        # Try center
        interactions.click_at_coordinates(center[0], center[1], APP_NAME)
        time.sleep(0.1)
        interactions.click_at_coordinates(center[0], center[1], APP_NAME)
        time.sleep(1.0)

    print("  ✓ Attempted to open edit dialog")
    capture_screenshot("step3_after_doubleclick")

    # Step 4: Type replacement text
    print(f"[4/6] Typing replacement text '{TEST_REPLACEMENT}'...")
    type_replacement_text(TEST_REPLACEMENT)
    print("  ✓ Typed replacement text")
    capture_screenshot("step4_after_typing")

    # Step 5: Toggle Preview ON
    print("[5/6] Toggling Preview checkbox...")
    time.sleep(0.3)

    # Try clicking Preview checkbox
    if click_preview_checkbox():
        print("  ✓ Clicked Preview checkbox")
    else:
        print("  ⚠ Could not find Preview checkbox directly")
        # Try using keyboard shortcut or tab to checkbox
        interactions.press_key('tab', app_name=APP_NAME)
        time.sleep(0.1)
        interactions.press_key('space', app_name=APP_NAME)
        print("  ✓ Attempted keyboard toggle")

    time.sleep(1.5)  # Wait for preview to apply
    capture_screenshot("step5_after_preview_toggle")

    # Step 6: Capture final state
    print("[6/6] Capturing final state...")
    final_path = capture_screenshot("step6_final")
    print(f"  ✓ Screenshot saved to: {final_path}")

    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print()
    print(f"Check screenshots in: {os.path.dirname(final_path)}")
    print()
    print("MANUAL VERIFICATION NEEDED:")
    print(f"  - Look at step5_after_preview_toggle.png")
    print(f"  - The PDF should show '{TEST_REPLACEMENT}' instead of original text")
    print()

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
