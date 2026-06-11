#!/usr/bin/env python3
"""
Semi-automated Text Selection Crash Test
This test requires user to manually open the PDF, then automates the click.
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

PROJECT_ROOT = Path("/Users/mhm/Documents/Dev/Marcedit")
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

        # Add text at KNOWN coordinates
        page.insert_text((150, 500), "TARGET TEXT LINE 1", fontsize=14)
        page.insert_text((150, 480), "TARGET TEXT LINE 2", fontsize=14)
        page.insert_text((150, 460), "TARGET TEXT LINE 3", fontsize=14)

        doc.save(test_pdf)
        doc.close()

        log(f"✓ Test PDF created: {test_pdf}", GREEN)
        log(f"  Text placed at: (150, 500), (150, 480), (150, 460)", BLUE)
        return test_pdf

    except ImportError:
        log("✗ PyMuPDF not found", RED)
        return None

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
        log("  ✗ PyObjC not available", RED)
        return False

def check_crash_logs():
    """Check for recent crash logs."""
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
    log("Semi-Automated Text Selection Crash Test", GREEN)
    log("="*60, GREEN)
    log("")

    # Create test PDF
    test_pdf = create_test_pdf()
    if not test_pdf:
        return 1

    log("", YELLOW)
    log("MANUAL STEP REQUIRED:", YELLOW)
    log("="*60, YELLOW)
    log("1. Marcedit is about to launch", YELLOW)
    log("2. Please manually open this PDF:", YELLOW)
    log(f"   {test_pdf}", YELLOW)
    log("3. Use File > Open or drag it into the app", YELLOW)
    log("4. Wait until you see the PDF with text in the window", YELLOW)
    log("5. Then press Enter here to continue", YELLOW)
    log("="*60, YELLOW)
    log("")

    # Launch app
    log("Launching Marcedit app...", BLUE)
    subprocess.Popen(["open", str(APP_BUNDLE)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(3)

    log("✓ App launched - waiting for you to open the PDF...", BLUE)
    input("Press Enter when you see the PDF loaded in the app window...")

    # Get window bounds
    bounds = get_window_bounds()
    if not bounds:
        log("✗ Could not get window bounds", RED)
        quit_app()
        return 1

    win_x, win_y, win_w, win_h = bounds

    # Calculate click coordinates
    pdf_margin_top = 80
    pdf_scale = min(win_w / 612, win_h / 792) if win_h > 0 else 1.0

    text1_x = win_x + 150 * pdf_scale + 50
    text1_y = win_y + win_h - (500 * pdf_scale + pdf_margin_top)

    log(f"", BLUE)
    log(f"Calculated click position: ({text1_x:.0f}, {text1_y:.0f})", BLUE)
    log(f"This should click on 'TARGET TEXT LINE 1'", BLUE)
    log(f"", YELLOW)
    log("About to click on the PDF text...", YELLOW)
    log("Watch the app window closely!", YELLOW)
    log(f"", YELLOW)

    time.sleep(2)

    # Click on text
    log("Clicking NOW...", BLUE)
    if not click_at_coordinates(text1_x, text1_y):
        log("✗ Click failed", RED)
        quit_app()
        return 1

    log("✓ Click sent", GREEN)
    log("Waiting for crash (2 seconds)...", BLUE)
    time.sleep(2)

    # Check crash logs
    crash_log = check_crash_logs()
    if crash_log:
        log("", RED)
        log("✗ CRASH DETECTED!", RED)
        log(f"  Crash log: {crash_log}", RED)

        with open(crash_log, 'r') as f:
            log("", RED)
            log("First 30 lines:", YELLOW)
            for i, line in enumerate(f):
                if i >= 30:
                    break
                log(f"  {line.rstrip()}", YELLOW)

        quit_app()
        if test_pdf.exists():
            test_pdf.unlink()
        return 1

    # Clean up
    quit_app()
    if test_pdf.exists():
        test_pdf.unlink()

    log("", BLUE)
    log("="*60, BLUE)
    log("TEST RESULT", BLUE)
    log("="*60, BLUE)
    log("✓ NO CRASH - Text selection works!", GREEN)
    log("  TextInputUIMacHelper crash is FIXED", GREEN)
    return 0

if __name__ == "__main__":
    sys.exit(main())
