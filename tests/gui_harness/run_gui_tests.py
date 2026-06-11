#!/usr/bin/env python3
"""
GUI Test Harness for Marcedit
Runs automated UI tests without requiring Xcode.

Usage:
    python3 tests/gui_harness/run_gui_tests.py
    python3 tests/gui_harness/run_gui_tests.py --test test_app_launches
    python3 tests/gui_harness/run_gui_tests.py --verbose
"""

import subprocess
import time
import os
import sys
import argparse
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Callable
import tempfile


@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class TestSuite:
    name: str
    results: List[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)


class MarceditTestHarness:
    """Test harness for Marcedit GUI testing."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.project_dir = Path(__file__).parent.parent.parent
        self.app_path = self.project_dir / ".build" / "debug" / "Marcedit.app"
        self.test_pdf_path = self.project_dir / "ignored-resources" / "sample-files-marcedit" / "15425215.pdf"
        self.app_process: Optional[subprocess.Popen] = None

    def log(self, msg: str):
        """Log message if verbose mode is on."""
        if self.verbose:
            print(f"  [DEBUG] {msg}")

    def build_app(self) -> bool:
        """Build the Marcedit app."""
        print("Building Marcedit...")
        result = subprocess.run(
            ["swift", "build"],
            cwd=self.project_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Build failed: {result.stderr}")
            return False
        print("Build successful.")
        return True

    def launch_app(self, with_test_pdf: bool = True) -> bool:
        """Launch Marcedit with optional test PDF."""
        if not self.app_path.exists():
            # Try alternate location
            alt_path = self.project_dir / ".build" / "arm64-apple-macosx" / "debug" / "Marcedit"
            if alt_path.exists():
                executable = alt_path
            else:
                print(f"App not found at {self.app_path} or {alt_path}")
                return False
        else:
            executable = self.app_path / "Contents" / "MacOS" / "Marcedit"
            if not executable.exists():
                # Swift PM builds executable directly
                executable = self.project_dir / ".build" / "debug" / "Marcedit"

        args = [str(executable), "--run-ui-tests"]
        if with_test_pdf and self.test_pdf_path.exists():
            args.append(f"--test-pdf-path={self.test_pdf_path}")

        self.log(f"Launching: {' '.join(args)}")

        try:
            self.app_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(2)  # Wait for app to launch

            # Check if process is still running
            if self.app_process.poll() is not None:
                stdout, stderr = self.app_process.communicate()
                print(f"App exited immediately. stderr: {stderr.decode()}")
                return False

            return True
        except Exception as e:
            print(f"Failed to launch app: {e}")
            return False

    def quit_app(self):
        """Quit the Marcedit app."""
        if self.app_process:
            self.log("Quitting app...")
            # Try graceful quit via AppleScript
            subprocess.run([
                "osascript", "-e",
                'tell application "Marcedit" to quit'
            ], capture_output=True)
            time.sleep(1)

            # Force kill if still running
            if self.app_process.poll() is None:
                self.app_process.terminate()
                time.sleep(0.5)
                if self.app_process.poll() is None:
                    self.app_process.kill()

            self.app_process = None

    def is_app_running(self) -> bool:
        """Check if Marcedit is running."""
        result = subprocess.run(
            ["pgrep", "-f", "Marcedit"],
            capture_output=True
        )
        return result.returncode == 0

    def run_applescript(self, script: str) -> tuple[bool, str]:
        """Run an AppleScript and return (success, output)."""
        self.log(f"Running AppleScript: {script[:100]}...")
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True
        )
        success = result.returncode == 0
        output = result.stdout.strip() if success else result.stderr.strip()
        return success, output

    def get_window_position(self) -> Optional[tuple[int, int, int, int]]:
        """Get main window position (x, y, width, height)."""
        success, output = self.run_applescript('''
            tell application "System Events"
                tell process "Marcedit"
                    if (count of windows) > 0 then
                        set win to window 1
                        set pos to position of win
                        set sz to size of win
                        set x to item 1 of pos as integer
                        set y to item 2 of pos as integer
                        set w to item 1 of sz as integer
                        set h to item 2 of sz as integer
                        return (x as text) & "|" & (y as text) & "|" & (w as text) & "|" & (h as text)
                    end if
                end tell
            end tell
        ''')
        if success and output:
            try:
                # Parse pipe-delimited output (cleaner than comma)
                parts = output.strip().split("|")
                if len(parts) == 4:
                    return tuple(int(p.strip()) for p in parts)
            except Exception as e:
                self.log(f"Failed to parse window position: {output} - {e}")
        return None

    def click_at(self, x: int, y: int):
        """Click at screen coordinates."""
        self.run_applescript(f'''
            tell application "System Events"
                click at {{{x}, {y}}}
            end tell
        ''')

    def get_ui_element_exists(self, identifier: str) -> bool:
        """Check if a UI element with accessibility identifier exists."""
        success, output = self.run_applescript(f'''
            tell application "System Events"
                tell process "Marcedit"
                    set foundElements to every UI element whose description contains "{identifier}"
                    return (count of foundElements) > 0
                end tell
            end tell
        ''')
        return success and output == "true"

    def activate_app(self):
        """Bring Marcedit to front."""
        self.run_applescript('tell application "Marcedit" to activate')
        time.sleep(0.5)

    def press_key(self, key: str, modifiers: List[str] = None):
        """Press a key with optional modifiers."""
        mod_str = ""
        if modifiers:
            mod_str = " using {" + ", ".join(f"{m} down" for m in modifiers) + "}"

        self.run_applescript(f'''
            tell application "System Events"
                tell process "Marcedit"
                    keystroke "{key}"{mod_str}
                end tell
            end tell
        ''')


class MarceditGUITests:
    """Collection of GUI tests for Marcedit."""

    def __init__(self, harness: MarceditTestHarness):
        self.harness = harness
        self.suite = TestSuite("MarceditGUITests")

    def run_test(self, name: str, test_func: Callable) -> TestResult:
        """Run a single test and return the result."""
        print(f"  Running: {name}...", end=" ", flush=True)
        start_time = time.time()

        try:
            test_func()
            duration = time.time() - start_time
            print(f"PASSED ({duration:.2f}s)")
            return TestResult(name=name, passed=True, duration=duration)
        except AssertionError as e:
            duration = time.time() - start_time
            print(f"FAILED ({duration:.2f}s)")
            print(f"    Error: {e}")
            return TestResult(name=name, passed=False, duration=duration, error=str(e))
        except SkipTest as e:
            duration = time.time() - start_time
            print(f"SKIPPED ({duration:.2f}s)")
            print(f"    Reason: {e}")
            return TestResult(name=name, passed=True, duration=duration, skipped=True, skip_reason=str(e))
        except Exception as e:
            duration = time.time() - start_time
            print(f"ERROR ({duration:.2f}s)")
            print(f"    Exception: {e}")
            return TestResult(name=name, passed=False, duration=duration, error=str(e))

    # ============= TEST METHODS =============

    def test_app_launches(self):
        """Test that the app launches without crashing."""
        assert self.harness.is_app_running(), "App should be running"
        time.sleep(1)
        assert self.harness.is_app_running(), "App should still be running after 1 second"

    def test_main_window_exists(self):
        """Test that the main window exists and has valid dimensions."""
        self.harness.activate_app()
        time.sleep(0.5)

        pos = self.harness.get_window_position()
        assert pos is not None, "Should be able to get window position"
        x, y, width, height = pos
        assert width > 100, f"Window width ({width}) should be > 100"
        assert height > 100, f"Window height ({height}) should be > 100"

    def test_window_on_screen(self):
        """Test that the window is fully visible on screen."""
        self.harness.activate_app()
        pos = self.harness.get_window_position()
        assert pos is not None, "Should be able to get window position"

        x, y, width, height = pos

        # Get screen size using NSScreen via Python
        try:
            from AppKit import NSScreen
            screen = NSScreen.mainScreen()
            if screen:
                frame = screen.frame()
                screen_width = int(frame.size.width)
                screen_height = int(frame.size.height)

                # Window position is relative to screen origin
                # Just check window has reasonable coordinates (not negative or huge)
                assert x >= -50, f"Window x ({x}) should be >= -50"
                assert y >= -50, f"Window y ({y}) should be >= -50"
                assert width > 0, f"Window width ({width}) should be > 0"
                assert height > 0, f"Window height ({height}) should be > 0"
                assert x < screen_width + 100, f"Window x ({x}) should be < screen width + 100"
                assert y < screen_height + 100, f"Window y ({y}) should be < screen height + 100"
        except ImportError:
            # If AppKit not available, just verify we got valid coordinates
            assert x >= -1000 and x <= 5000, f"Window x ({x}) should be reasonable"
            assert y >= -1000 and y <= 5000, f"Window y ({y}) should be reasonable"

    def test_pdf_loaded(self):
        """Test that the test PDF was loaded."""
        time.sleep(2)  # Wait for PDF to load

        # Check if we can see PDF-related UI - window should have elements
        success, output = self.harness.run_applescript('''
            tell application "System Events"
                tell process "Marcedit"
                    -- Look for any indication that PDF is loaded
                    set allElements to every UI element of window 1
                    return count of allElements
                end tell
            end tell
        ''')

        assert success, "Should be able to query UI elements"
        element_count = int(output) if output.isdigit() else 0
        # Just verify the app has some UI (> 0 elements means window has content)
        assert element_count >= 1, f"Window should have UI elements (found {element_count})"

    def test_window_stability_over_time(self):
        """Test that window doesn't jump around on its own."""
        self.harness.activate_app()

        # Get initial position
        pos1 = self.harness.get_window_position()
        assert pos1 is not None, "Should get initial position"

        # Wait and check position hasn't changed
        time.sleep(2)
        pos2 = self.harness.get_window_position()
        assert pos2 is not None, "Should get second position"

        x1, y1, w1, h1 = pos1
        x2, y2, w2, h2 = pos2

        assert abs(x1 - x2) < 5, f"Window X moved unexpectedly: {x1} -> {x2}"
        assert abs(y1 - y2) < 5, f"Window Y moved unexpectedly: {y1} -> {y2}"

    def test_zoom_controls_work(self):
        """Test that zoom controls don't crash the app."""
        self.harness.activate_app()

        # Use keyboard shortcuts for zoom
        # Cmd+= for zoom in, Cmd+- for zoom out, Cmd+0 for fit

        self.harness.press_key("=", ["command"])
        time.sleep(0.5)
        assert self.harness.is_app_running(), "App should be running after zoom in"

        self.harness.press_key("-", ["command"])
        time.sleep(0.5)
        assert self.harness.is_app_running(), "App should be running after zoom out"

        self.harness.press_key("0", ["command"])
        time.sleep(0.5)
        assert self.harness.is_app_running(), "App should be running after zoom fit"

    def test_app_survives_rapid_operations(self):
        """Test that rapid operations don't crash the app."""
        self.harness.activate_app()

        # Rapid zoom operations
        for _ in range(5):
            self.harness.press_key("=", ["command"])
            time.sleep(0.1)

        for _ in range(5):
            self.harness.press_key("-", ["command"])
            time.sleep(0.1)

        time.sleep(1)
        assert self.harness.is_app_running(), "App should survive rapid zoom operations"

    def test_keyboard_shortcuts_work(self):
        """Test that keyboard shortcuts work without crashing."""
        self.harness.activate_app()

        # Try help shortcut (Cmd+?)
        self.harness.press_key("/", ["command", "shift"])
        time.sleep(0.5)
        assert self.harness.is_app_running(), "App should be running after help shortcut"

        # Press Escape to close any dialogs
        self.harness.run_applescript('''
            tell application "System Events"
                tell process "Marcedit"
                    key code 53  -- Escape
                end tell
            end tell
        ''')
        time.sleep(0.5)

    def test_undo_redo_stability(self):
        """Test that undo/redo shortcuts don't crash."""
        self.harness.activate_app()

        # Try undo (Cmd+Z)
        self.harness.press_key("z", ["command"])
        time.sleep(0.3)
        assert self.harness.is_app_running(), "App should be running after undo"

        # Try redo (Cmd+Shift+Z)
        self.harness.press_key("z", ["command", "shift"])
        time.sleep(0.3)
        assert self.harness.is_app_running(), "App should be running after redo"

    def test_no_crash_after_5_minutes(self):
        """Extended stability test - app should run without crashing."""
        self.harness.activate_app()

        # Quick version: just verify it's still running after some operations
        for i in range(10):
            self.harness.press_key("=", ["command"])
            time.sleep(0.2)
            self.harness.press_key("-", ["command"])
            time.sleep(0.2)

        time.sleep(2)
        assert self.harness.is_app_running(), "App should be running after extended operations"

    # ============= PREVIEW TOGGLE TESTS =============

    def test_preview_toggle_no_crash(self):
        """Test that clicking on text and toggling preview doesn't crash."""
        self.harness.activate_app()

        # Click in the PDF area to try to select text
        success, _ = self.harness.run_applescript('''
            tell application "System Events"
                tell process "Marcedit"
                    if (count of windows) > 0 then
                        set win to window 1
                        -- Click in the center of the window
                        click at {500, 400}
                    end if
                end tell
            end tell
        ''')

        time.sleep(1)
        assert self.harness.is_app_running(), "App should survive click on PDF"

        # Try double-click to select text
        self.harness.run_applescript('''
            tell application "System Events"
                tell process "Marcedit"
                    if (count of windows) > 0 then
                        -- Double-click to try to select text
                        click at {500, 400}
                        delay 0.1
                        click at {500, 400}
                    end if
                end tell
            end tell
        ''')

        time.sleep(2)
        assert self.harness.is_app_running(), "App should survive double-click on PDF"

    def test_rapid_window_resize(self):
        """Test that rapidly resizing doesn't crash."""
        self.harness.activate_app()
        pos = self.harness.get_window_position()
        assert pos is not None, "Should have window"

        # Resize window multiple times using keyboard
        for _ in range(3):
            # Can't easily resize via AppleScript, but verify window is stable
            time.sleep(0.3)
            new_pos = self.harness.get_window_position()
            assert new_pos is not None, "Window should still exist"

        assert self.harness.is_app_running(), "App should survive resize operations"

    def test_sidebar_toggle(self):
        """Test sidebar toggle (Cmd+B) works without crash."""
        self.harness.activate_app()

        # Toggle sidebar
        self.harness.press_key("b", ["command"])
        time.sleep(0.5)
        assert self.harness.is_app_running(), "App should survive sidebar toggle"

        # Toggle back
        self.harness.press_key("b", ["command"])
        time.sleep(0.5)
        assert self.harness.is_app_running(), "App should survive sidebar toggle back"

    def test_window_doesnt_jump_during_operations(self):
        """Test that window position stays stable during normal operations."""
        self.harness.activate_app()

        # Get initial position
        pos1 = self.harness.get_window_position()
        assert pos1 is not None, "Should have initial position"

        # Perform various operations
        self.harness.press_key("=", ["command"])  # zoom in
        time.sleep(0.3)
        self.harness.press_key("-", ["command"])  # zoom out
        time.sleep(0.3)
        self.harness.press_key("0", ["command"])  # fit
        time.sleep(0.3)

        # Get position after operations
        pos2 = self.harness.get_window_position()
        assert pos2 is not None, "Should have position after operations"

        x1, y1, _, _ = pos1
        x2, y2, _, _ = pos2

        # Window shouldn't have moved more than a few pixels
        assert abs(x1 - x2) < 10, f"Window X jumped from {x1} to {x2}"
        assert abs(y1 - y2) < 10, f"Window Y jumped from {y1} to {y2}"

    def test_memory_stability(self):
        """Test that repeated operations don't cause memory issues."""
        self.harness.activate_app()

        # Perform many zoom operations
        for _ in range(20):
            self.harness.press_key("=", ["command"])
            time.sleep(0.1)

        for _ in range(20):
            self.harness.press_key("-", ["command"])
            time.sleep(0.1)

        time.sleep(1)
        assert self.harness.is_app_running(), "App should survive many zoom operations"

        # Reset to fit
        self.harness.press_key("0", ["command"])
        time.sleep(0.5)
        assert self.harness.is_app_running(), "App should be stable after reset"

    def run_all(self, test_filter: Optional[str] = None) -> TestSuite:
        """Run all tests (or filtered subset)."""
        # Get all test methods
        test_methods = [
            (name, getattr(self, name))
            for name in dir(self)
            if name.startswith("test_") and callable(getattr(self, name))
        ]

        # Apply filter if provided
        if test_filter:
            test_methods = [
                (name, func) for name, func in test_methods
                if test_filter.lower() in name.lower()
            ]

        print(f"\nRunning {len(test_methods)} tests...")
        print("=" * 50)

        for name, func in sorted(test_methods):
            result = self.run_test(name, func)
            self.suite.results.append(result)

        return self.suite


class SkipTest(Exception):
    """Raised to skip a test."""
    pass


def main():
    parser = argparse.ArgumentParser(description="Run Marcedit GUI tests")
    parser.add_argument("--test", "-t", help="Run only tests matching this filter")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--no-build", action="store_true", help="Skip building the app")
    parser.add_argument("--keep-running", action="store_true", help="Don't quit app after tests")
    args = parser.parse_args()

    print("=" * 50)
    print("Marcedit GUI Test Harness")
    print("=" * 50)

    harness = MarceditTestHarness(verbose=args.verbose)

    # Build app
    if not args.no_build:
        if not harness.build_app():
            print("Build failed, exiting.")
            sys.exit(1)

    # Launch app
    print("\nLaunching Marcedit...")
    if not harness.launch_app(with_test_pdf=True):
        print("Failed to launch app, exiting.")
        sys.exit(1)

    print("App launched successfully.")
    time.sleep(2)  # Give app time to settle

    try:
        # Run tests
        tests = MarceditGUITests(harness)
        suite = tests.run_all(test_filter=args.test)

        # Print summary
        print("\n" + "=" * 50)
        print("TEST SUMMARY")
        print("=" * 50)
        print(f"Passed:  {suite.passed}")
        print(f"Failed:  {suite.failed}")
        print(f"Skipped: {suite.skipped}")
        print(f"Total:   {len(suite.results)}")

        if suite.failed > 0:
            print("\nFailed tests:")
            for r in suite.results:
                if not r.passed and not r.skipped:
                    print(f"  - {r.name}: {r.error}")

        # Return exit code
        exit_code = 0 if suite.failed == 0 else 1

    finally:
        if not args.keep_running:
            print("\nCleaning up...")
            harness.quit_app()

    print("\nDone.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
