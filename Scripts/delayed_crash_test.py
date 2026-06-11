#!/usr/bin/env python3
"""
Delayed Text Selection Crash Test
Waits 30 seconds for user to manually open the PDF, then automates the crash test.
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
MAGENTA = '\033[0;35m'
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
        page = doc.new_page(width=612, height=792)

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
        cleaned = result.stdout.strip().replace(", ", ",").replace(",,", ",")
        parts = cleaned.split(",")

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

        move_event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, CGPoint(screen_x, screen_y), 0)
        CGEventPost(kCGHIDEventTap, move_event)

        time.sleep(0.1)

        down_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, CGPoint(screen_x, screen_y), 0)
        CGEventPost(kCGHIDEventTap, down_event)

        time.sleep(0.05)

        up_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, CGPoint(screen_x, screen_y), 0)
        CGEventPost(kCGHIDEventTap, up_event)

        return True

    except ImportError:
        log("  ✗ PyObjC not available", RED)
        return False

def check_app_still_running():
    """Check if app is still running (didn't crash)."""
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
    """Check for recent crash logs."""
    crash_dir = Path.home() / "Library" / "Logs" / "DiagnosticReports"

    if not crash_dir.exists():
        return None

    now = time.time()
    recent_crashes = []

    for crash_file in crash_dir.glob("Marcedit*.crash"):
        file_time = crash_file.stat().st_mtime
        if now - file_time < 120:
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

def countdown_timer(seconds):
    """Display a countdown timer."""
    for remaining in range(seconds, 0, -1):
        mins, secs = divmod(remaining, 60)
        timer = f'\r⏳ Time remaining to open PDF: {mins:02d}:{secs:02d} '
        print(f"{MAGENTA}{timer}{NC}", end='', flush=True)
        time.sleep(1)

    print('\r' + ' ' * 60 + '\r', end='', flush=True)

def main():
    log("="*60, GREEN)
    log("Delayed Text Selection Crash Test", GREEN)
    log("="*60, GREEN)
    log("")

    # Create test PDF
    test_pdf = create_test_pdf()
    if not test_pdf:
        return 1

    log("", MAGENTA)
    log("╔══════════════════════════════════════════════════════════╗", MAGENTA)
    log("║          IMPORTANT: MANUAL STEP REQUIRED                ║", MAGENTA)
    log("╚══════════════════════════════════════════════════════════╝", MAGENTA)
    log("", MAGENTA)
    log("Marcedit will launch in 3 seconds...", YELLOW)
    log("You have 30 seconds to:", YELLOW)
    log(f"  1. Open this PDF: {test_pdf}", YELLOW)
    log("  2. Use File > Open or drag & drop", YELLOW)
    log("  3. Wait until you see the text in the window", YELLOW)
    log("")
    log("The test will automatically click on the text after 30 seconds", YELLOW)
    log("", MAGENTA)
    log("="*60, MAGENTA)
    log("")

    time.sleep(3)

    # Launch app
    log("Launching Marcedit app...", BLUE)
    subprocess.Popen(["open", str(APP_BUNDLE)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)

    log("✓ App launched - starting 30 second countdown...", GREEN)
    log("", BLUE)

    # Countdown
    countdown_timer(30)

    log("", BLUE)
    log("⏰ Countdown complete - proceeding with test...", BLUE)
    log("")

    # Get window bounds
    bounds = get_window_bounds()
    if not bounds:
        log("✗ Could not get window bounds", RED)
        log("  This might mean the app isn't running or window isn't visible", RED)
        quit_app()
        return 1

    win_x, win_y, win_w, win_h = bounds

    # Calculate click coordinates
    pdf_margin_top = 80
    pdf_scale = min(win_w / 612, win_h / 792) if win_h > 0 else 1.0

    text1_x = win_x + 150 * pdf_scale + 50
    text1_y = win_y + win_h - (500 * pdf_scale + pdf_margin_top)

    log(f"Calculated click position: ({text1_x:.0f}, {text1_y:.0f})", BLUE)
    log(f"This should click on 'TARGET TEXT LINE 1'", BLUE)
    log("", YELLOW)
    log("🖱️  Clicking on PDF text in 3...", YELLOW)
    time.sleep(1)
    log("🖱️  Clicking on PDF text in 2...", YELLOW)
    time.sleep(1)
    log("🖱️  Clicking on PDF text in 1...", YELLOW)
    time.sleep(1)
    log("", YELLOW)

    # Click on text
    log("CLICKING NOW!", BLUE)
    if not click_at_coordinates(text1_x, text1_y):
        log("✗ Click failed", RED)
        quit_app()
        return 1

    log("✓ Click sent", GREEN)
    log("Waiting for crash (3 seconds)...", BLUE)
    time.sleep(3)

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
        log("First 30 lines:", YELLOW)

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
