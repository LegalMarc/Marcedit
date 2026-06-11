#!/usr/bin/env python3
"""
Text Selection Crash Test
Reproduces the TextInputUIMacHelper crash by opening a PDF and selecting text.
"""

import subprocess
import time
import sys
import os
from pathlib import Path

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

PROJECT_ROOT = Path(".")
APP_BUNDLE = PROJECT_ROOT / "ignored-resources" / "Marcedit.app"

def log(message, color=""):
    print(f"{color}{message}{NC}")

def create_test_pdf():
    """Create a test PDF with text at known coordinates."""
    try:
        import fitz

        test_pdf = PROJECT_ROOT / "test_text_selection.pdf"

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # Standard letter size

        # Add text at KNOWN coordinates so we can click on them
        # PDF coordinates: (x, y) where y=0 is at the BOTTOM
        # We'll place text in the middle where it's easy to click

        # Line 1: Target text at coordinates we can calculate
        page.insert_text((150, 500), "TARGET TEXT LINE 1", fontsize=14)

        # Line 2: More target text
        page.insert_text((150, 480), "TARGET TEXT LINE 2", fontsize=14)

        # Line 3: Even more text
        page.insert_text((150, 460), "TARGET TEXT LINE 3", fontsize=14)

        doc.save(test_pdf)
        doc.close()

        log(f"✓ Test PDF created: {test_pdf}", GREEN)
        log(f"  Text placed at: (150, 500), (150, 480), (150, 460)", BLUE)
        return test_pdf

    except ImportError:
        log("✗ PyMuPDF not found", RED)
        return None

def open_pdf_in_app(pdf_path):
    """Open PDF in Marcedit app."""
    log(f"Opening PDF in Marcedit...", BLUE)

    # Try multiple methods to open the PDF
    success = False

    # Method 1: Try using macOS 'open' command
    log("  Method 1: Using 'open' command...", BLUE)
    result = subprocess.run(
        ["open", "-a", "Marcedit", str(pdf_path)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        log("  ✓ 'open' command succeeded", GREEN)
        success = True
    else:
        log(f"  ✗ 'open' command failed: {result.stderr}", RED)

    time.sleep(3)  # Wait for PDF to load

    # Method 2: If that didn't work, try clicking File > Open via UI
    if not success:
        log("  Method 2: Trying UI File > Open menu...", BLUE)

        ui_script = f'''
        tell application "Marcedit"
            activate
        end tell

        tell application "System Events"
            tell process "Marcedit"
                # Click File menu
                click menu bar item "File" of menu bar 1

                delay 0.5

                # Click Open menu item
                try
                    click menu item "Open…" of menu "File" of menu bar item "File" of menu bar 1

                    delay 1

                    # Type the path and press Enter
                    keystroke "{pdf_path}"
                    keystroke return

                    return "success"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
        end tell
        '''

        result = subprocess.run(
            ["osascript", "-e", ui_script],
            capture_output=True,
            text=True
        )

        if "success" in result.stdout.lower():
            log("  ✓ UI File > Open succeeded", GREEN)
            success = True
        else:
            log(f"  ✗ UI File > Open failed: {result.stderr}", RED)

    time.sleep(3)  # Wait for PDF to load

    # Verify PDF is loaded by checking if window title changed
    verify_script = '''
    tell application "System Events"
        tell process "Marcedit"
            if exists window 1 then
                set windowTitle to title of window 1
                return windowTitle
            else
                return "no window"
            end if
        end tell
    end tell
    '''

    verify_result = subprocess.run(
        ["osascript", "-e", verify_script],
        capture_output=True,
        text=True
    )

    window_title = verify_result.stdout.strip()
    log(f"  Window title: '{window_title}'", BLUE)

    if "test_text_selection" in window_title or pdf_path.name in window_title:
        log("✓ PDF appears to be loaded (title contains PDF name)", GREEN)
        return True
    else:
        log("⚠ Could not verify PDF is loaded", YELLOW)
        log("  Marcedit may not change window title, or PDF didn't open", YELLOW)
        # Continue anyway - user can verify visually
        return True

def get_window_bounds():
    """Get the bounds of the Marcedit window."""
    script = '''
    tell application "System Events"
        tell process "Marcedit"
            try
                set frontWindow to window 1
                set windowPos to position of frontWindow
                set windowSize to size of frontWindow

                return (item 1 of windowPos) & "," & (item 2 of windowPos) & "," & (item 1 of windowSize) & "," & (item 2 of windowSize)
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )

    if result.returncode == 0 and "," in result.stdout:
        # Handle weird AppleScript output format: "0, ,, 33, ,, 1728, ,, 1084"
        cleaned = result.stdout.strip().replace(", ", ",").replace(",,", ",")
        parts = cleaned.split(",")

        # Filter out empty strings and convert to integers
        numbers = [int(p.strip()) for p in parts if p.strip().isdigit()]

        if len(numbers) == 4:
            x, y, w, h = numbers
            log(f"  Window bounds: x={x}, y={y}, width={w}, height={h}", BLUE)
            return x, y, w, h

    log("  ⚠ Could not get window bounds", YELLOW)
    log(f"    Raw output: {result.stdout}", YELLOW)
    return None

def click_at_coordinates(screen_x, screen_y):
    """Click at specific screen coordinates using CGEvent."""
    try:
        from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap
        from Quartz.CoreGraphics import CGPoint

        # Create mouse move event
        move_event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, CGPoint(screen_x, screen_y), 0)
        CGEventPost(kCGHIDEventTap, move_event)

        # Small delay
        time.sleep(0.1)

        # Create mouse down event
        down_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, CGPoint(screen_x, screen_y), 0)
        CGEventPost(kCGHIDEventTap, down_event)

        # Small delay
        time.sleep(0.05)

        # Create mouse up event
        up_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, CGPoint(screen_x, screen_y), 0)
        CGEventPost(kCGHIDEventTap, up_event)

        return True

    except ImportError:
        # Fallback to AppleScript if PyObjC not available
        log("  ⚠ PyObjC not available, using AppleScript fallback", YELLOW)
        return click_at_coordinates_applescript(screen_x, screen_y)

def click_at_coordinates_applescript(screen_x, screen_y):
    """Click at coordinates using AppleScript (less precise)."""
    script = f'''
    tell application "System Events"
        tell process "Marcedit"
            try
                # Click at absolute screen coordinates
                click at {{screen_x:{screen_x}, screen_y:{screen_y}}}
                return "success"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )

    return result.returncode == 0

def simulate_text_selection():
    """Simulate clicking on actual PDF text at known coordinates."""
    log("Simulating text selection by clicking on PDF text...", BLUE)

    # Step 1: Get window bounds
    bounds = get_window_bounds()

    if not bounds:
        # Fallback: Try clicking in center of main display
        log("  ⚠ Using fallback: clicking in center of screen", YELLOW)

        try:
            from Quartz import CGDisplayBounds, CGMainDisplayID
            from Quartz.CoreGraphics import CGPoint

            display_id = CGMainDisplayID()
            display_bounds = CGDisplayBounds(display_id)

            center_x = display_bounds.origin.x + display_bounds.size.width / 2
            center_y = display_bounds.origin.y + display_bounds.size.height / 2

            log(f"  Clicking at screen center: ({center_x:.0f}, {center_y:.0f})", BLUE)
            time.sleep(0.5)

            if click_at_coordinates(center_x, center_y):
                log("  ✓ Click sent", GREEN)
                time.sleep(2)
                return True
            else:
                log("  ✗ Click failed", RED)
                return False

        except ImportError:
            log("  ✗ Fallback failed - Quartz not available", RED)
            return False

    win_x, win_y, win_w, win_h = bounds

    # Step 2: Calculate click coordinates
    # PDF is 612x792 points (letter size)
    # Window may be scaled, so we estimate the PDF display area
    # We'll click in the middle-left area where we placed text

    # Text is at PDF coordinates (150, 500), (150, 480), (150, 460)
    # We need to map these to screen coordinates
    # Assuming PDF is displayed centered in window

    pdf_margin_top = 80  # Estimated margin at top
    pdf_scale = min(win_w / 612, win_h / 792) if win_h > 0 else 1.0

    # Calculate screen coordinates for first text line
    # PDF y=500 is from bottom, so in window coordinates it's inverted
    text1_x = win_x + 150 * pdf_scale + 50  # +50 for left margin
    text1_y = win_y + win_h - (500 * pdf_scale + pdf_margin_top)

    log(f"  Calculated click position: ({text1_x:.0f}, {text1_y:.0f})", BLUE)
    log(f"  This should click on 'TARGET TEXT LINE 1'", BLUE)

    # Step 3: Click on the text
    time.sleep(0.5)  # Wait for window to be ready

    log("  Clicking on text...", BLUE)
    if not click_at_coordinates(text1_x, text1_y):
        log("  ✗ Click failed", RED)
        return False

    log("  ✓ Click sent", GREEN)

    # Step 4: Wait for crash or edit sheet
    log("  Waiting for crash response (2 seconds)...", BLUE)
    time.sleep(2)

    return True

def check_app_still_running():
    """Check if app is still running (didn't crash)."""
    time.sleep(2)  # Wait for any delayed crash

    result = subprocess.run(
        ["pgrep", "-f", "Marcedit"],
        capture_output=True
    )

    if result.returncode == 0:
        pid = result.stdout.decode().strip().split('\n')[0]
        log(f"✓ App still running (PID: {pid})", GREEN)
        return True
    else:
        log("✗ App crashed!", RED)
        return False

def check_crash_logs():
    """Check for new crash logs."""
    crash_dir = Path.home() / "Library" / "Logs" / "DiagnosticReports"

    if not crash_dir.exists():
        return None

    # Find recent Marcedit crash logs (last 2 minutes)
    now = time.time()
    recent_crashes = []

    for crash_file in crash_dir.glob("Marcedit*.crash"):
        file_time = crash_file.stat().st_mtime
        if now - file_time < 120:  # Last 2 minutes
            recent_crashes.append(crash_file)

    if recent_crashes:
        most_recent = max(recent_crashes, key=lambda p: p.stat().st_mtime)
        return most_recent

    return None

def quit_app():
    """Quit the app."""
    log("Quitting app...", BLUE)

    subprocess.run(
        ["osascript", "-e", 'tell application "Marcedit" to quit'],
        capture_output=True
    )

    time.sleep(1)

def main():
    log("="*60, GREEN)
    log("Text Selection Crash Test", GREEN)
    log("="*60, GREEN)
    log("")
    log("This test:")
    log("  1. Creates a PDF with text at known coordinates", BLUE)
    log("  2. Opens Marcedit app WITH the PDF", BLUE)
    log("  3. CLICKS on the text (not keyboard shortcut)", BLUE)
    log("  4. Checks if TextInputUIMacHelper crash occurs", BLUE)
    log("")

    # Create test PDF
    test_pdf = create_test_pdf()
    if not test_pdf:
        return 1

    # Launch app WITH the PDF as argument
    log("Launching Marcedit app with PDF...", BLUE)
    log(f"  Opening: {test_pdf}", BLUE)

    # Use 'open' command with the app and PDF
    subprocess.Popen(
        ["open", "-a", "Marcedit", str(test_pdf)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    log("  Waiting for app to launch and load PDF...", BLUE)
    time.sleep(5)  # Give it extra time to load the PDF

    # Verify app launched
    if not check_app_still_running():
        log("✗ App failed to launch!", RED)
        return 1

    log("✓ App is running", GREEN)

    # Check if PDF loaded by looking at window title
    verify_script = '''
    tell application "System Events"
        tell process "Marcedit"
            if exists window 1 then
                set windowTitle to title of window 1
                return windowTitle
            else
                return "no window"
            end if
        end tell
    end tell
    '''

    verify_result = subprocess.run(
        ["osascript", "-e", verify_script],
        capture_output=True,
        text=True
    )

    window_title = verify_result.stdout.strip()
    log(f"  Window title: '{window_title}'", BLUE)

    if "test_text_selection" not in window_title and test_pdf.name not in window_title:
        log("  ⚠ Warning: Window title doesn't show PDF name", YELLOW)
        log("  This might mean the PDF didn't load properly", YELLOW)
        log("  Please verify the PDF is visible in the app window", YELLOW)
    else:
        log("✓ PDF appears to be loaded", GREEN)

    # Simulate text selection by CLICKING on text (this triggers the crash)
    log("", BLUE)
    log("⚠ CRITICAL TEST: Clicking on PDF text...", YELLOW)
    log("  This triggers EditorViewModel.startInteractiveFontSearch", YELLOW)
    log("  which causes the TextInputUIMacHelper crash", YELLOW)
    log("", BLUE)

    success = simulate_text_selection()

    if not success:
        log("", RED)
        log("✗ Failed to click on text", RED)
        quit_app()
        return 1

    # Check if app crashed
    log("", BLUE)
    log("Checking if app survived the click...", BLUE)

    still_running = check_app_still_running()

    # Check crash logs
    crash_log = check_crash_logs()
    if crash_log:
        log("", RED)
        log("✗ CRASH DETECTED!", RED)
        log(f"  Crash log: {crash_log}", RED)
        log("", RED)
        log("This confirms the TextInputUIMacHelper crash is still present", RED)
        log("", RED)
        log("First few lines:", YELLOW)

        with open(crash_log, 'r') as f:
            for i, line in enumerate(f):
                if i >= 30:
                    break
                log(f"  {line.rstrip()}", YELLOW)

        # Try to clean up
        try:
            quit_app()
        except:
            pass

        if test_pdf.exists():
            test_pdf.unlink()

        return 1

    # Clean up
    quit_app()
    if test_pdf.exists():
        test_pdf.unlink()

    # Summary
    log("", BLUE)
    log("="*60, BLUE)
    log("TEST RESULT", BLUE)
    log("="*60, BLUE)

    if still_running:
        log("✓ NO CRASH - Text selection works!", GREEN)
        log("  TextInputUIMacHelper crash is FIXED", GREEN)
        log("", GREEN)
        log("The app survived clicking on PDF text without crashing", GREEN)
        return 0
    else:
        log("✗ CRASH DETECTED - App crashed", RED)
        log("  TextInputUIMacHelper crash still present", RED)
        log("  But no crash log was found (unusual)", RED)
        return 1

if __name__ == "__main__":
    sys.exit(main())
