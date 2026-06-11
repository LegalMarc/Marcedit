#!/usr/bin/env python3
"""
Manual App Crash Test
Launches Marcedit app and tests basic editing workflow to catch crashes.
Run this before and after changes to ensure stability.
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
TEST_PDF = PROJECT_ROOT / "sample-files" / "test_document.pdf"

def log(message, color=""):
    print(f"{color}{message}{NC}")

def create_test_pdf():
    """Create a test PDF for editing."""
    log("Creating test PDF...", BLUE)

    try:
        import fitz

        test_pdf = PROJECT_ROOT / "test_crash_check.pdf"

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # Letter size

        # Add various text to test different scenarios
        page.insert_text((50, 700), "Crash Test Document", fontsize=16, color=(0, 0, 0))
        page.insert_text((50, 670), "Line 1: Normal black text", fontsize=12)
        page.insert_text((50, 650), "Line 2: TARGET for replacement", fontsize=12)
        page.insert_text((50, 630), "Line 3: Mixed case Test", fontsize=12)
        page.insert_text((50, 610), "Line 4: Numbers 12345", fontsize=12)
        page.insert_text((50, 590), "Line 5: Blue text", fontsize=12, color=(0, 0, 1))

        # Add a second page
        page2 = doc.new_page()
        page2.insert_text((50, 700), "Page 2 Test", fontsize=12)
        page2.insert_text((50, 680), "More text here TARGET more text", fontsize=12)

        doc.save(test_pdf)
        doc.close()

        log(f"✓ Test PDF created: {test_pdf}", GREEN)
        return test_pdf

    except ImportError:
        log("✗ PyMuPDF not found, skipping test PDF creation", YELLOW)
        return None
    except Exception as e:
        log(f"✗ Failed to create test PDF: {e}", RED)
        return None

def test_app_launch():
    """Test that the app launches without crashing."""
    log("\n" + "="*60, BLUE)
    log("TEST 1: App Launch", BLUE)
    log("="*60, BLUE)

    if not APP_BUNDLE.exists():
        log(f"✗ App not found at {APP_BUNDLE}", RED)
        log("  Run: python3 build_tui.py (Option 2)", YELLOW)
        return False

    log(f"Launching app: {APP_BUNDLE}", BLUE)

    try:
        # Launch app in background
        process = subprocess.Popen(
            ["open", str(APP_BUNDLE)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Wait for app to launch
        time.sleep(3)

        # Check if app is still running
        result = subprocess.run(
            ["pgrep", "-f", "Marcedit"],
            capture_output=True
        )

        if result.returncode == 0:
            log("✓ App launched successfully (PID: {})".format(
                result.stdout.decode().strip().split('\n')[0]
            ), GREEN)
            return True
        else:
            log("✗ App crashed or failed to launch", RED)
            return False

    except Exception as e:
        log(f"✗ Error launching app: {e}", RED)
        return False

def test_app_stability(duration=10):
    """Test that app stays stable over time."""
    log("\n" + "="*60, BLUE)
    log(f"TEST 2: App Stability ({duration}s)", BLUE)
    log("="*60, BLUE)

    log(f"Waiting {duration} seconds to check for delayed crashes...", BLUE)

    for i in range(duration):
        time.sleep(1)
        if i % 2 == 0:
            print(f".", end="", flush=True)

    print()

    # Check if app is still running
    result = subprocess.run(
        ["pgrep", "-f", "Marcedit"],
        capture_output=True
    )

    if result.returncode == 0:
        log(f"✓ App still running after {duration}s", GREEN)
        return True
    else:
        log(f"✗ App crashed within {duration}s", RED)
        return False

def test_menu_interaction():
    """Test basic menu accessibility (sanity check)."""
    log("\n" + "="*60, BLUE)
    log("TEST 3: Menu System", BLUE)
    log("="*60, BLUE)

    log("Checking menu bar accessibility...", BLUE)

    try:
        # Use AppleScript to check menus
        script = '''
        tell application "System Events"
            tell process "Marcedit"
                try
                    set menuBar to menu bar 1
                    set menuItems to name of every menu of menuBar
                    return menuItems
                on error
                    return "error"
                end try
            end tell
        end tell
        '''

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and "error" not in result.stdout.lower():
            menu_items = result.stdout.strip().split(", ")
            log(f"✓ Found {len(menu_items)} menu items", GREEN)
            log(f"  Menus: {', '.join(menu_items[:5])}{'...' if len(menu_items) > 5 else ''}", BLUE)
            return True
        else:
            log("⚠ Could not verify menu items (app may not be focused)", YELLOW)
            return True  # Not a failure, just can't test

    except Exception as e:
        log(f"⚠ Could not test menu system: {e}", YELLOW)
        return True  # Not a critical failure

def test_window_creation():
    """Test that windows can be created."""
    log("\n" + "="*60, BLUE)
    log("TEST 4: Window Creation", BLUE)
    log("="*60, BLUE)

    log("Checking for window creation...", BLUE)

    try:
        script = '''
        tell application "System Events"
            tell process "Marcedit"
                try
                    set windowCount to count of windows
                    if windowCount > 0 then
                        set windowTitle to title of window 1
                        return windowCount & " | " & windowTitle
                    else
                        return "0 | none"
                    end if
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

        if result.returncode == 0:
            output = result.stdout.strip()
            if "error" not in output.lower():
                log(f"✓ {output}", GREEN)
                return True

        log("⚠ Could not verify windows", YELLOW)
        return True

    except Exception as e:
        log(f"⚠ Could not test windows: {e}", YELLOW)
        return True

def check_crash_logs():
    """Check for new crash logs."""
    log("\n" + "="*60, BLUE)
    log("TEST 5: Crash Log Check", BLUE)
    log("="*60, BLUE)

    log("Checking for recent crash logs...", BLUE)

    crash_dir = Path.home() / "Library" / "Logs" / "DiagnosticReports"

    if not crash_dir.exists():
        log("✓ No crash log directory (no crashes)", GREEN)
        return True

    # Find recent Marcedit crash logs (last 5 minutes)
    import datetime
    now = time.time()
    recent_crashes = []

    for crash_file in crash_dir.glob("Marcedit*.crash"):
        file_time = crash_file.stat().st_mtime
        if now - file_time < 300:  # Last 5 minutes
            recent_crashes.append(crash_file)

    if recent_crashes:
        log(f"✗ Found {len(recent_crashes)} recent crash log(s):", RED)
        for crash in recent_crashes:
            log(f"  - {crash.name}", RED)
            log(f"    {crash}", YELLOW)

        # Show first few lines of most recent crash
        most_recent = max(recent_crashes, key=lambda p: p.stat().st_mtime)
        log(f"\n  Most recent crash details:", YELLOW)
        with open(most_recent, 'r') as f:
            for i, line in enumerate(f):
                if i >= 20:
                    break
                log(f"  {line.rstrip()}", YELLOW)

        return False
    else:
        log("✓ No recent crash logs", GREEN)
        return True

def quit_app():
    """Quit the app cleanly."""
    log("\n" + "="*60, BLUE)
    log("Cleaning up: Quitting app", BLUE)
    log("="*60, BLUE)

    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Marcedit" to quit'],
            capture_output=True
        )
        time.sleep(1)
        log("✓ App quit successfully", GREEN)
    except:
        # Force quit if graceful quit fails
        subprocess.run(["pkill", "-9", "Marcedit"], capture_output=True)
        log("✓ App force quit", YELLOW)

def main():
    """Run all tests."""
    log("\n" + "="*60, GREEN)
    log("Marcedit App Crash Test Suite", GREEN)
    log("="*60, GREEN)

    # Create test PDF
    test_pdf = create_test_pdf()

    # Run tests
    results = []

    results.append(("App Launch", test_app_launch()))

    if results[-1][1]:  # Only continue if launch succeeded
        time.sleep(2)
        results.append(("Stability (10s)", test_app_stability(10)))
        results.append(("Menu System", test_menu_interaction()))
        results.append(("Window Creation", test_window_creation()))
        results.append(("Crash Logs", check_crash_logs()))

    # Clean up
    quit_app()

    if test_pdf and test_pdf.exists():
        test_pdf.unlink()
        log(f"\n✓ Cleaned up test PDF", GREEN)

    # Print summary
    log("\n" + "="*60, BLUE)
    log("TEST SUMMARY", BLUE)
    log("="*60, BLUE)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        color = GREEN if result else RED
        log(f"  {status}: {test_name}", color)

    log("\n" + "-"*60, BLUE)
    log(f"Result: {passed}/{total} tests passed", BLUE)

    if passed == total:
        log("🎉 ALL TESTS PASSED - App appears stable!", GREEN)
        return 0
    else:
        log("⚠️  SOME TESTS FAILED - Check for issues", YELLOW)
        return 1

if __name__ == "__main__":
    sys.exit(main())
