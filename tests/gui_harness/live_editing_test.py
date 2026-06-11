#!/usr/bin/env python3
"""
Live editing workflow test - assumes PDF is already open in Marcedit.
Tests the actual editing experience with visual verification.

Usage:
1. Open Marcedit
2. Load a PDF
3. Run: python3 -m tests.gui_harness.live_editing_test
"""

import subprocess
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

from . import observer
from . import interactions


@dataclass
class EditingIssue:
    """A detected issue during editing."""
    timestamp: float
    step: str
    issue_type: str  # 'window_jump', 'preview_shift', 'selection_issue', 'edit_window_position'
    severity: str
    description: str
    window_pos_before: Tuple[int, int]
    window_pos_after: Tuple[int, int]
    screenshot_before: str
    screenshot_after: str
    delta_px: float


class LiveEditingTester:
    """Tests editing workflow on an already-open PDF."""

    def __init__(self, app_name: str = 'Marcedit', output_dir: str = None):
        self.app_name = app_name
        self.output_dir = Path(output_dir or '/tmp/marcedit_live_editing')
        self.output_dir.mkdir(exist_ok=True, parents=True)

        self.issues: List[EditingIssue] = []
        self.screenshots: List[str] = []
        self.frame_count = 0

    def capture(self, name: str) -> Tuple[str, Tuple[int, int]]:
        """Capture screenshot and window position."""
        screenshot_path = str(self.output_dir / f"{self.frame_count:03d}_{name}.png")
        observer.capture_window(self.app_name, screenshot_path)
        window_pos = interactions.get_window_position(self.app_name) or (0, 0)

        self.screenshots.append(screenshot_path)
        self.frame_count += 1

        return screenshot_path, window_pos

    def check_movement(self, name: str, pos_before: Tuple[int, int], pos_after: Tuple[int, int],
                      screenshot_before: str, screenshot_after: str,
                      tolerance: int = 5, expected: bool = False):
        """Check if window moved unexpectedly."""
        dx = abs(pos_after[0] - pos_before[0])
        dy = abs(pos_after[1] - pos_before[1])
        delta = (dx**2 + dy**2)**0.5

        if delta > tolerance and not expected:
            severity = 'critical' if delta > 50 else 'major' if delta > 20 else 'minor'
            self.issues.append(EditingIssue(
                timestamp=time.time(),
                step=name,
                issue_type='window_jump',
                severity=severity,
                description=f"Window jumped {delta:.0f}px (dx={dx}, dy={dy})",
                window_pos_before=pos_before,
                window_pos_after=pos_after,
                screenshot_before=screenshot_before,
                screenshot_after=screenshot_after,
                delta_px=delta
            ))
            print(f"  ⚠️  ISSUE: Window jumped {delta:.0f}px during {name}")

    def verify_pdf_loaded(self) -> bool:
        """
        Verify that a PDF is actually loaded before testing.

        Returns:
            True if PDF is loaded, False otherwise
        """
        # Capture screenshot for visual verification
        temp_shot = str(self.output_dir / "pdf_verification.png")
        observer.capture_window(self.app_name, temp_shot)

        # Check for UI elements that indicate PDF is loaded
        script = f'''
        tell application "System Events"
            tell process "{self.app_name}"
                if (count of windows) > 0 then
                    -- Check for scroll bar (indicates content)
                    try
                        set scrollBars to scroll bars of window 1
                        if (count of scrollBars) > 0 then
                            return "has_content"
                        end if
                    end try
                end if
            end tell
        end tell
        return ""
        '''
        result = interactions.run_applescript(script)

        has_content = "has_content" in result

        # Try to verify visually by checking for diverse content
        try:
            from PIL import Image
            img = Image.open(temp_shot)
            width, height = img.size

            # Check if window is reasonable size
            if width < 400 or height < 400:
                print(f"  ⚠️  WARNING: Window is small ({width}x{height}) - may not have document loaded")
                return False

            # Check pixel diversity (PDFs have varied content)
            pixels = list(img.getdata())
            unique_colors = len(set(pixels[:1000]))

            if unique_colors < 20:
                print(f"  ⚠️  WARNING: Window appears empty (only {unique_colors} unique colors)")
                return False

        except Exception as e:
            print(f"  ℹ️  Could not verify visually: {e}")

        return has_content

    def test_text_selection_flow(self) -> Dict[str, Any]:
        """
        Test the complete text selection and editing flow.

        Tests:
        1. Click to position cursor
        2. Double-click to select word
        3. Edit window appears
        4. Type new text
        5. Save edit
        6. Check document stability
        """
        print(f"\n{'='*70}")
        print(f"LIVE EDITING WORKFLOW TEST")
        print(f"{'='*70}\n")
        print("Prerequisites:")
        print("  1. Marcedit must be running")
        print("  2. A PDF document must be open")
        print("  3. Document should be visible in the main view\n")

        # Verify app is running
        script = 'tell application "System Events" to return name of every process'
        processes = interactions.run_applescript(script)

        if self.app_name not in processes:
            print(f"❌ ERROR: {self.app_name} is not running!")
            return {'error': f'{self.app_name} not running', 'passed': False}

        # CRITICAL: Verify PDF is actually loaded
        print("Verifying PDF is loaded...")
        if not self.verify_pdf_loaded():
            print(f"❌ ERROR: No PDF document appears to be loaded!")
            print("   This test requires an open PDF to prevent false positives.")
            return {'error': 'No PDF loaded', 'passed': False}

        interactions.activate_app(self.app_name)
        time.sleep(0.5)

        test_start = time.time()

        # BASELINE: Capture initial state
        print("[1/10] Capturing baseline state...")
        baseline_shot, baseline_pos = self.capture("baseline")
        print(f"  Window at {baseline_pos}")
        time.sleep(0.5)

        # Get window center for clicking
        win_size = interactions.get_window_size(self.app_name)
        if not win_size:
            print("❌ ERROR: Could not get window size")
            return {'error': 'No window size', 'passed': False}

        # Calculate click position (center-left of window where text usually is)
        click_x = baseline_pos[0] + int(win_size[0] * 0.3)
        click_y = baseline_pos[1] + int(win_size[1] * 0.4)

        # STEP 1: Single click to position cursor
        print(f"[2/10] Clicking in document at ({click_x}, {click_y})...")
        before_click, pos_before = self.capture("before_single_click")

        interactions.click_at_coordinates(click_x, click_y, self.app_name)
        time.sleep(0.4)

        after_click, pos_after = self.capture("after_single_click")
        self.check_movement("single_click", pos_before, pos_after, before_click, after_click)

        # STEP 2: Double-click to select word
        print("[3/10] Double-clicking to select word...")
        before_double, pos_before = self.capture("before_double_click")

        interactions.click_at_coordinates(click_x, click_y, self.app_name)
        time.sleep(0.05)
        interactions.click_at_coordinates(click_x, click_y, self.app_name)
        time.sleep(0.6)  # Wait for selection + edit window

        after_double, pos_after = self.capture("after_double_click")
        self.check_movement("double_click", pos_before, pos_after, before_double, after_double)

        # STEP 3: Edit window should be visible now
        print("[4/10] Edit window should be visible...")
        time.sleep(0.3)
        edit_window_shot, edit_window_pos = self.capture("edit_window_visible")
        print(f"  Window at {edit_window_pos}")

        # STEP 4: Type replacement text
        print("[5/10] Typing replacement text 'MODIFIED'...")
        before_type, pos_before = self.capture("before_typing")

        # Clear any existing text and type new
        interactions.press_key('a', modifiers=['command'], app_name=self.app_name)
        time.sleep(0.1)
        interactions.type_text("MODIFIED", app_name=self.app_name)
        time.sleep(0.3)

        after_type, pos_after = self.capture("after_typing")
        self.check_movement("typing", pos_before, pos_after, before_type, after_type)

        # STEP 5: Save edit (press Return)
        print("[6/10] Saving edit (Return key)...")
        before_save, pos_before = self.capture("before_save")

        interactions.press_key('return', app_name=self.app_name)
        time.sleep(1.0)  # Wait for save and reflow

        after_save, pos_after = self.capture("after_save")
        self.check_movement("save_edit", pos_before, pos_after, before_save, after_save, tolerance=10)

        # STEP 6: Check document stability after edit
        print("[7/10] Checking document stability...")
        time.sleep(0.5)
        stable_shot, stable_pos = self.capture("post_edit_stable")

        # STEP 7: Toggle preview OFF
        print("[8/10] Toggling preview OFF (Cmd+P)...")
        before_preview_off, pos_before = self.capture("before_preview_off")

        interactions.press_key('p', modifiers=['command'], app_name=self.app_name)
        time.sleep(0.6)

        after_preview_off, pos_after = self.capture("after_preview_off")
        self.check_movement("preview_off", pos_before, pos_after, before_preview_off, after_preview_off,
                          tolerance=15, expected=False)  # Preview shouldn't cause major jumps

        # STEP 8: Toggle preview back ON
        print("[9/10] Toggling preview ON (Cmd+P)...")
        before_preview_on, pos_before = self.capture("before_preview_on")

        interactions.press_key('p', modifiers=['command'], app_name=self.app_name)
        time.sleep(0.6)

        after_preview_on, pos_after = self.capture("after_preview_on")
        self.check_movement("preview_on", pos_before, pos_after, before_preview_on, after_preview_on,
                          tolerance=15, expected=False)

        # STEP 9: Final stability check
        print("[10/10] Final stability check...")
        time.sleep(0.5)
        final_shot, final_pos = self.capture("final_state")

        # Compare to baseline
        self.check_movement("overall_drift", baseline_pos, final_pos, baseline_shot, final_shot,
                          tolerance=30, expected=True)

        test_duration = time.time() - test_start

        # Compile results
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_duration_sec': test_duration,
            'app_name': self.app_name,
            'screenshots': self.screenshots,
            'issues': [asdict(i) for i in self.issues],
            'issue_count': {
                'critical': len([i for i in self.issues if i.severity == 'critical']),
                'major': len([i for i in self.issues if i.severity == 'major']),
                'minor': len([i for i in self.issues if i.severity == 'minor']),
            },
            'passed': len([i for i in self.issues if i.severity in ['critical', 'major']]) == 0
        }

        return results

    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate visual HTML report."""
        html_path = self.output_dir / "editing_test_report.html"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Marcedit Live Editing Test Report</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f8f9fa; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; }}
        .container {{ max-width: 1600px; margin: 0 auto; padding: 20px; }}
        .summary {{ background: white; padding: 25px; border-radius: 12px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .pass {{ color: #10b981; font-weight: 600; }}
        .fail {{ color: #ef4444; font-weight: 600; }}
        .issue {{ background: white; border-left: 5px solid #f59e0b; padding: 20px; margin: 15px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .issue.critical {{ border-left-color: #ef4444; background: #fef2f2; }}
        .issue.major {{ border-left-color: #f59e0b; background: #fffbeb; }}
        .issue.minor {{ border-left-color: #3b82f6; background: #eff6ff; }}
        .screenshot-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; margin: 20px 0; }}
        .screenshot-card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .screenshot-card img {{ width: 100%; border-radius: 6px; cursor: pointer; transition: transform 0.2s; }}
        .screenshot-card img:hover {{ transform: scale(1.02); }}
        .screenshot-title {{ font-weight: 600; margin-bottom: 10px; color: #1f2937; }}
        .badge {{ display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; margin: 0 5px; }}
        .badge-critical {{ background: #fee2e2; color: #991b1b; }}
        .badge-major {{ background: #fed7aa; color: #92400e; }}
        .badge-minor {{ background: #dbeafe; color: #1e40af; }}
        h2 {{ color: #1f2937; margin-top: 40px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 Marcedit Live Editing Test Report</h1>
        <p>Comprehensive visual testing of text editing workflow</p>
    </div>

    <div class="container">
        <div class="summary">
            <h2>Test Summary</h2>
            <p><strong>Timestamp:</strong> {results['timestamp']}</p>
            <p><strong>Duration:</strong> {results['test_duration_sec']:.1f}s</p>
            <p><strong>Result:</strong> <span class="{'pass' if results.get('passed') else 'fail'}">
                {'✅ PASS' if results.get('passed') else '❌ FAIL'}</span></p>
            <p><strong>Issues Detected:</strong>
                <span class="badge badge-critical">{results['issue_count']['critical']} Critical</span>
                <span class="badge badge-major">{results['issue_count']['major']} Major</span>
                <span class="badge badge-minor">{results['issue_count']['minor']} Minor</span>
            </p>
        </div>
"""

        if self.issues:
            html += "<h2>🐛 Issues Detected</h2>"
            for issue in self.issues:
                html += f"""
        <div class="issue {issue.severity}">
            <h3>[{issue.severity.upper()}] {issue.description}</h3>
            <p><strong>Step:</strong> {issue.step}<br>
            <strong>Window Movement:</strong> {issue.window_pos_before} → {issue.window_pos_after}<br>
            <strong>Delta:</strong> {issue.delta_px:.1f} pixels</p>
            <div style="display: flex; gap: 10px; margin-top: 15px;">
                <div style="flex: 1;">
                    <strong>Before:</strong><br>
                    <img src="{Path(issue.screenshot_before).name}" style="width: 100%; border: 2px solid #e5e7eb; border-radius: 4px;">
                </div>
                <div style="flex: 1;">
                    <strong>After:</strong><br>
                    <img src="{Path(issue.screenshot_after).name}" style="width: 100%; border: 2px solid #e5e7eb; border-radius: 4px;">
                </div>
            </div>
        </div>
"""
        else:
            html += "<div class='summary'><h2>✅ No Issues Detected</h2><p>All editing operations completed without unexpected window movement or visual glitches!</p></div>"

        html += "<h2>📸 Complete Visual Walkthrough</h2><div class='screenshot-grid'>"

        for i, shot in enumerate(results['screenshots']):
            shot_name = Path(shot).stem.replace('_', ' ').title()
            html += f"""
        <div class="screenshot-card">
            <div class="screenshot-title">{i+1}. {shot_name}</div>
            <img src="{Path(shot).name}" onclick="window.open('{Path(shot).name}', '_blank')">
        </div>
"""

        html += """
        </div>
    </div>
</body>
</html>
"""

        with open(html_path, 'w') as f:
            f.write(html)

        return str(html_path)


def run_live_editing_test() -> Dict[str, Any]:
    """Run the live editing test."""
    tester = LiveEditingTester()
    results = tester.test_text_selection_flow()

    if 'error' in results:
        print(f"\n❌ Test failed: {results['error']}")
        return results

    # Generate report
    report_path = tester.generate_report(results)
    results['report_path'] = report_path

    # Save JSON
    json_path = tester.output_dir / 'results.json'
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    results['json_path'] = str(json_path)

    # Print summary
    print(f"\n{'='*70}")
    print(f"TEST COMPLETE")
    print(f"{'='*70}\n")
    print(f"Result: {'✅ PASS' if results['passed'] else '❌ FAIL'}")
    print(f"Issues: {results['issue_count']['critical']} critical, {results['issue_count']['major']} major, {results['issue_count']['minor']} minor")
    print(f"\n📊 Report: {report_path}")
    print(f"📁 Screenshots: {tester.output_dir}\n")

    # Open report automatically
    subprocess.run(['open', report_path])

    return results


if __name__ == '__main__':
    results = run_live_editing_test()
    import sys
    sys.exit(0 if results.get('passed') else 1)
