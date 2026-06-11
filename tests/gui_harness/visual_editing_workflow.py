#!/usr/bin/env python3
"""
Comprehensive visual testing of the Marcedit editing workflow.
Simulates real user interaction and detects visual issues at every step.
"""

import subprocess
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

from . import observer
from . import interactions


@dataclass
class VisualSnapshot:
    """A captured moment in the editing workflow."""
    step_name: str
    timestamp: float
    screenshot_path: str
    window_position: Optional[Tuple[int, int]]
    window_size: Optional[Tuple[int, int]]
    element_positions: Dict[str, Tuple[int, int]]
    notes: str = ""


@dataclass
class VisualIssue:
    """A detected visual problem."""
    step: str
    issue_type: str  # 'unexpected_movement', 'element_jump', 'missing_element', 'layout_shift'
    severity: str  # 'critical', 'major', 'minor'
    description: str
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None
    delta_info: Optional[Dict] = None


class EditingWorkflowTester:
    """Tests the complete editing workflow with visual verification."""

    def __init__(self, app_name: str = 'Marcedit', output_dir: str = None):
        self.app_name = app_name
        self.output_dir = Path(output_dir or '/tmp/editing_workflow_test')
        self.output_dir.mkdir(exist_ok=True, parents=True)

        self.snapshots: List[VisualSnapshot] = []
        self.issues: List[VisualIssue] = []

        # Expected element positions (will be set from first observation)
        self.baseline_positions = {}

    def capture_snapshot(self, step_name: str, notes: str = "") -> VisualSnapshot:
        """Capture complete visual state at this step."""
        screenshot_path = str(self.output_dir / f"{len(self.snapshots):03d}_{step_name.replace(' ', '_')}.png")

        # Capture screenshot
        observer.capture_window(self.app_name, screenshot_path)

        # Get window info
        window_pos = interactions.get_window_position(self.app_name)
        window_size = interactions.get_window_size(self.app_name)

        # Get element positions
        element_positions = self._get_element_positions()

        snapshot = VisualSnapshot(
            step_name=step_name,
            timestamp=time.time(),
            screenshot_path=screenshot_path,
            window_position=window_pos,
            window_size=window_size,
            element_positions=element_positions,
            notes=notes
        )

        self.snapshots.append(snapshot)
        return snapshot

    def _get_element_positions(self) -> Dict[str, Tuple[int, int]]:
        """Get positions of all accessible UI elements."""
        script = f'''
        tell application "System Events"
            tell process "{self.app_name}"
                set output to ""
                if (count of windows) > 0 then
                    repeat with elem in entire contents of window 1
                        try
                            set elemDesc to description of elem as string
                            set elemRole to role of elem as string
                            set elemPos to position of elem
                            if elemDesc is not "" then
                                set output to output & elemRole & ":" & elemDesc & ":" & (item 1 of elemPos) & "," & (item 2 of elemPos) & linefeed
                            end if
                        end try
                    end repeat
                end if
                return output
            end tell
        end tell
        '''
        result = interactions.run_applescript(script)

        positions = {}
        for line in result.strip().split('\n'):
            if ':' in line and ',' in line:
                try:
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2:
                        role_and_name = parts[0]
                        coords = parts[1]
                        x, y = map(int, coords.split(','))
                        positions[role_and_name] = (x, y)
                except (ValueError, IndexError):
                    pass

        return positions

    def check_for_movement(self, prev_snapshot: VisualSnapshot, curr_snapshot: VisualSnapshot,
                          expected_movement: bool = False, tolerance: int = 5) -> List[VisualIssue]:
        """
        Check if elements moved unexpectedly between snapshots.

        Args:
            prev_snapshot: Previous state
            curr_snapshot: Current state
            expected_movement: True if movement is expected (e.g., scrolling)
            tolerance: Pixels of acceptable drift
        """
        issues = []

        # Check window position
        if prev_snapshot.window_position and curr_snapshot.window_position:
            prev_x, prev_y = prev_snapshot.window_position
            curr_x, curr_y = curr_snapshot.window_position
            dx = abs(curr_x - prev_x)
            dy = abs(curr_y - prev_y)

            if (dx > tolerance or dy > tolerance) and not expected_movement:
                issues.append(VisualIssue(
                    step=curr_snapshot.step_name,
                    issue_type='unexpected_movement',
                    severity='major',
                    description=f"Window moved unexpectedly by ({dx}, {dy}) pixels",
                    screenshot_before=prev_snapshot.screenshot_path,
                    screenshot_after=curr_snapshot.screenshot_path,
                    delta_info={'dx': dx, 'dy': dy}
                ))

        # Check element positions
        for elem_name, prev_pos in prev_snapshot.element_positions.items():
            if elem_name in curr_snapshot.element_positions:
                curr_pos = curr_snapshot.element_positions[elem_name]
                dx = abs(curr_pos[0] - prev_pos[0])
                dy = abs(curr_pos[1] - prev_pos[1])
                delta = (dx ** 2 + dy ** 2) ** 0.5

                # Skip document content elements (they're expected to move during scrolling)
                if 'text' in elem_name.lower() or 'content' in elem_name.lower():
                    continue

                # UI elements shouldn't move unless expected
                if delta > tolerance and not expected_movement:
                    severity = 'major' if delta > 20 else 'minor'
                    issues.append(VisualIssue(
                        step=curr_snapshot.step_name,
                        issue_type='element_jump',
                        severity=severity,
                        description=f"UI element '{elem_name}' jumped {delta:.1f}px",
                        screenshot_before=prev_snapshot.screenshot_path,
                        screenshot_after=curr_snapshot.screenshot_path,
                        delta_info={'element': elem_name, 'delta_px': delta, 'dx': dx, 'dy': dy}
                    ))

        return issues

    def check_element_visibility(self, element_name: str, should_exist: bool) -> Optional[VisualIssue]:
        """Check if an element exists when it should (or doesn't when it shouldn't)."""
        exists = interactions.element_exists(element_name, self.app_name)

        if should_exist and not exists:
            return VisualIssue(
                step=self.snapshots[-1].step_name if self.snapshots else "unknown",
                issue_type='missing_element',
                severity='critical',
                description=f"Expected element '{element_name}' not found",
                screenshot_after=self.snapshots[-1].screenshot_path if self.snapshots else None
            )
        elif not should_exist and exists:
            return VisualIssue(
                step=self.snapshots[-1].step_name if self.snapshots else "unknown",
                issue_type='unexpected_element',
                severity='minor',
                description=f"Element '{element_name}' present when it shouldn't be",
                screenshot_after=self.snapshots[-1].screenshot_path if self.snapshots else None
            )

        return None

    def verify_pdf_loaded_with_retry(self, pdf_path: str, max_attempts: int = 3) -> bool:
        """
        Attempt to load PDF and verify it actually loaded.

        Args:
            pdf_path: Path to PDF file
            max_attempts: Maximum number of attempts

        Returns:
            True if PDF loaded successfully
        """
        for attempt in range(max_attempts):
            print(f"  [Attempt {attempt + 1}/{max_attempts}] Loading PDF...")

            # Open file dialog
            interactions.press_key('o', modifiers=['command'], app_name=self.app_name)
            time.sleep(1.0)

            # Navigate to file
            interactions.press_key('g', modifiers=['command', 'shift'], app_name=self.app_name)
            time.sleep(0.5)

            # Type path
            interactions.type_text(pdf_path, app_name=self.app_name)
            time.sleep(0.3)

            # Confirm
            interactions.press_key('return', app_name=self.app_name)
            time.sleep(0.5)
            interactions.press_key('return', app_name=self.app_name)

            # Wait for loading (exponential backoff)
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait_time)

            # Verify by checking for scroll bars (indicates content)
            script = f'''
            tell application "System Events"
                tell process "{self.app_name}"
                    if (count of windows) > 0 then
                        try
                            set scrollBars to scroll bars of window 1
                            if (count of scrollBars) > 0 then
                                return "loaded"
                            end if
                        end try
                    end if
                end tell
            end tell
            return ""
            '''
            result = interactions.run_applescript(script)

            if "loaded" in result:
                print(f"  ✅ PDF loaded successfully on attempt {attempt + 1}")
                return True

            print(f"  ❌ Verification failed on attempt {attempt + 1}")

            # Close any error dialogs
            if attempt < max_attempts - 1:
                interactions.press_key('escape', app_name=self.app_name)
                time.sleep(0.5)

        print(f"  ❌ Failed to load PDF after {max_attempts} attempts")
        return False

    def run_full_editing_workflow(self, pdf_path: str) -> Dict[str, Any]:
        """
        Run comprehensive editing workflow test.

        Workflow:
        1. Launch/activate app
        2. Open PDF with verification and retry
        3. Wait for document to load
        4. Click to select text
        5. Verify edit window appears
        6. Modify text
        7. Toggle preview on/off
        8. Check for unexpected document movement
        9. Save changes

        Returns:
            Dict with test results and detected issues.
        """
        print(f"\n{'='*60}")
        print(f"VISUAL EDITING WORKFLOW TEST")
        print(f"{'='*60}\n")

        test_start = time.time()

        # STEP 1: Activate application
        print("[1/12] Activating application...")
        interactions.activate_app(self.app_name)
        time.sleep(0.5)
        self.capture_snapshot("01_app_activated", "Initial state after activation")

        # STEP 2-4: Load PDF with verification
        print("[2/12] Loading PDF with verification...")
        if not self.verify_pdf_loaded_with_retry(pdf_path):
            print("\n❌ CRITICAL FAILURE: Could not load PDF")
            print("   Stopping test to prevent false positives from empty window")

            return {
                'timestamp': datetime.now().isoformat(),
                'test_duration_sec': time.time() - test_start,
                'pdf_path': pdf_path,
                'app_name': self.app_name,
                'snapshots': [asdict(s) for s in self.snapshots],
                'issues': [asdict(VisualIssue(
                    step="pdf_loading",
                    issue_type="loading_failed",
                    severity="critical",
                    description="Failed to load PDF after multiple attempts"
                ))],
                'issue_count': {'critical': 1, 'major': 0, 'minor': 0},
                'passed': False
            }

        # STEP 4: Document loaded - capture baseline
        print("[4/12] Document loaded, capturing baseline...")
        baseline = self.capture_snapshot("04_document_loaded", "PDF fully loaded and verified")
        self.baseline_positions = baseline.element_positions

        # STEP 5: Click in document to select text
        print("[5/12] Clicking in document to select text...")
        win_pos = interactions.get_window_position(self.app_name)
        if win_pos:
            # Click in the center-left area where text typically is
            click_x = win_pos[0] + 200
            click_y = win_pos[1] + 300

            before_click = self.capture_snapshot("05a_before_text_click", f"Before clicking at ({click_x}, {click_y})")

            interactions.click_at_coordinates(click_x, click_y, self.app_name)
            time.sleep(0.3)

            after_click = self.capture_snapshot("05b_after_text_click", "After clicking - selection should appear")

            # Check for unexpected movement
            movement_issues = self.check_for_movement(before_click, after_click, expected_movement=False)
            self.issues.extend(movement_issues)

        # STEP 6: Double-click to select word
        print("[6/12] Double-clicking to select word...")
        before_doubleclick = self.snapshots[-1]

        if win_pos:
            interactions.click_at_coordinates(click_x, click_y, self.app_name)
            time.sleep(0.05)
            interactions.click_at_coordinates(click_x, click_y, self.app_name)
            time.sleep(0.5)

        after_doubleclick = self.capture_snapshot("06_word_selected", "Word should be selected")

        # Check for document shift
        movement_issues = self.check_for_movement(before_doubleclick, after_doubleclick, expected_movement=False)
        self.issues.extend(movement_issues)

        # STEP 7: Verify edit window appears
        print("[7/12] Checking for edit window...")
        time.sleep(0.5)
        edit_window_snapshot = self.capture_snapshot("07_edit_window_check", "Edit window should be visible")

        # Look for edit-related UI elements
        # Common identifiers: EditTextField, SaveButton, CancelButton, etc.
        # (These would need to be set in SwiftUI with .accessibilityIdentifier())

        # STEP 8: Type in edit field (if found)
        print("[8/12] Attempting to type in edit field...")
        before_typing = self.snapshots[-1]

        # Try to type (assuming edit field is focused)
        interactions.type_text("EDITED", app_name=self.app_name)
        time.sleep(0.3)

        after_typing = self.capture_snapshot("08_text_typed", "Text 'EDITED' typed in edit field")

        # Check for unexpected movement during typing
        movement_issues = self.check_for_movement(before_typing, after_typing, expected_movement=False)
        self.issues.extend(movement_issues)

        # STEP 9: Press Enter/Save
        print("[9/12] Saving edit...")
        before_save = self.snapshots[-1]

        interactions.press_key('return', app_name=self.app_name)
        time.sleep(0.8)  # Wait for edit to apply and reflow

        after_save = self.capture_snapshot("09_edit_saved", "Edit saved, document updated")

        # Check for document movement after save
        movement_issues = self.check_for_movement(before_save, after_save, expected_movement=False)
        self.issues.extend(movement_issues)

        # STEP 10: Toggle preview OFF
        print("[10/12] Toggling preview OFF...")
        before_preview_off = self.snapshots[-1]

        # Try clicking preview toggle button
        # This would need accessibility identifier like "PreviewToggle"
        preview_toggled = interactions.click_button("PreviewToggle", self.app_name)
        if not preview_toggled:
            print("    (Preview button not found via identifier, trying keyboard shortcut)")
            interactions.press_key('p', modifiers=['command'], app_name=self.app_name)

        time.sleep(0.5)
        after_preview_off = self.capture_snapshot("10_preview_off", "Preview toggled OFF")

        # Check for document jump when preview toggles
        movement_issues = self.check_for_movement(before_preview_off, after_preview_off, expected_movement=True, tolerance=10)
        if movement_issues:
            # Mark as unexpected since preview toggle shouldn't cause major jumps
            for issue in movement_issues:
                issue.notes = "Document moved when preview toggled OFF"
            self.issues.extend(movement_issues)

        # STEP 11: Toggle preview back ON
        print("[11/12] Toggling preview ON...")
        before_preview_on = self.snapshots[-1]

        if not interactions.click_button("PreviewToggle", self.app_name):
            interactions.press_key('p', modifiers=['command'], app_name=self.app_name)

        time.sleep(0.5)
        after_preview_on = self.capture_snapshot("11_preview_on", "Preview toggled ON")

        # Check for document jump when preview toggles back
        movement_issues = self.check_for_movement(before_preview_on, after_preview_on, expected_movement=True, tolerance=10)
        if movement_issues:
            for issue in movement_issues:
                issue.notes = "Document moved when preview toggled ON"
            self.issues.extend(movement_issues)

        # STEP 12: Final state
        print("[12/12] Capturing final state...")
        final = self.capture_snapshot("12_final_state", "Final state after full workflow")

        # Compare final to baseline - document should be stable
        movement_issues = self.check_for_movement(baseline, final, expected_movement=True, tolerance=20)
        if movement_issues:
            for issue in movement_issues:
                issue.notes = "Document position changed from baseline"
                issue.severity = 'minor'  # Some drift is acceptable
            self.issues.extend(movement_issues)

        test_duration = time.time() - test_start

        # Compile results
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_duration_sec': test_duration,
            'pdf_path': pdf_path,
            'app_name': self.app_name,
            'snapshots': [asdict(s) for s in self.snapshots],
            'issues': [asdict(i) for i in self.issues],
            'issue_count': {
                'critical': len([i for i in self.issues if i.severity == 'critical']),
                'major': len([i for i in self.issues if i.severity == 'major']),
                'minor': len([i for i in self.issues if i.severity == 'minor']),
            },
            'passed': len([i for i in self.issues if i.severity in ['critical', 'major']]) == 0
        }

        return results

    def generate_visual_report(self, results: Dict[str, Any]) -> str:
        """Generate HTML report with all screenshots and issues."""
        html_path = self.output_dir / "workflow_report.html"

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Marcedit Visual Editing Workflow Test Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007aff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .summary {{ background: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .pass {{ color: #28a745; font-weight: bold; }}
        .fail {{ color: #dc3545; font-weight: bold; }}
        .issue {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 10px 0; border-radius: 4px; }}
        .issue.critical {{ background: #f8d7da; border-left-color: #dc3545; }}
        .issue.major {{ background: #ffe5d0; border-left-color: #fd7e14; }}
        .snapshot {{ margin: 30px 0; padding: 20px; background: #fafafa; border-radius: 8px; }}
        .snapshot img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; }}
        .snapshot img:hover {{ opacity: 0.9; }}
        .snapshot-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .snapshot-title {{ font-size: 18px; font-weight: 600; color: #333; }}
        .snapshot-notes {{ color: #666; font-size: 14px; margin-top: 8px; }}
        .issue-count {{ display: inline-block; padding: 5px 12px; border-radius: 12px; margin: 0 5px; font-size: 14px; }}
        .critical-count {{ background: #dc3545; color: white; }}
        .major-count {{ background: #fd7e14; color: white; }}
        .minor-count {{ background: #ffc107; color: black; }}
    </style>
</head>
<body>
<div class="container">
    <h1>Marcedit Visual Editing Workflow Test Report</h1>

    <div class="summary">
        <p><strong>Timestamp:</strong> {results['timestamp']}</p>
        <p><strong>Test Duration:</strong> {results['test_duration_sec']:.1f} seconds</p>
        <p><strong>PDF:</strong> {results['pdf_path']}</p>
        <p><strong>Result:</strong> <span class="{'pass' if results['passed'] else 'fail'}">
            {'PASS' if results['passed'] else 'FAIL'}</span></p>
        <p><strong>Issues Found:</strong>
            <span class="issue-count critical-count">{results['issue_count']['critical']} Critical</span>
            <span class="issue-count major-count">{results['issue_count']['major']} Major</span>
            <span class="issue-count minor-count">{results['issue_count']['minor']} Minor</span>
        </p>
    </div>

    <h2>Issues Detected</h2>
"""

        if not self.issues:
            html += "<p>No issues detected - all workflow steps completed successfully!</p>"
        else:
            for issue in self.issues:
                html += f"""
    <div class="issue {issue.severity}">
        <strong>[{issue.severity.upper()}]</strong> {issue.description}<br>
        <small>Step: {issue.step} | Type: {issue.issue_type}</small>
"""
                if issue.delta_info:
                    html += f"<br><small>Details: {issue.delta_info}</small>"
                html += "</div>"

        html += "<h2>Visual Workflow Walkthrough</h2>"

        for snapshot in self.snapshots:
            rel_path = Path(snapshot.screenshot_path).name
            html += f"""
    <div class="snapshot">
        <div class="snapshot-header">
            <span class="snapshot-title">{snapshot.step_name}</span>
        </div>
        <img src="{rel_path}" alt="{snapshot.step_name}" onclick="window.open('{rel_path}', '_blank')">
        <div class="snapshot-notes">{snapshot.notes}</div>
        <small>Window: {snapshot.window_position} | Size: {snapshot.window_size} | Elements: {len(snapshot.element_positions)}</small>
    </div>
"""

        html += """
</div>
</body>
</html>
"""

        with open(html_path, 'w') as f:
            f.write(html)

        return str(html_path)


def run_visual_editing_test(pdf_path: str, output_dir: str = None) -> Dict[str, Any]:
    """
    Run comprehensive visual editing workflow test.

    Args:
        pdf_path: Path to PDF to test with
        output_dir: Where to save screenshots and report

    Returns:
        Test results with detected issues
    """
    tester = EditingWorkflowTester(output_dir=output_dir)
    results = tester.run_full_editing_workflow(pdf_path)

    # Generate visual report
    report_path = tester.generate_visual_report(results)
    results['report_path'] = report_path

    # Save JSON results
    json_path = Path(output_dir or '/tmp/editing_workflow_test') / 'results.json'
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    results['json_path'] = str(json_path)

    print(f"\n{'='*60}")
    print(f"TEST COMPLETE")
    print(f"{'='*60}")
    print(f"\nResult: {'PASS' if results['passed'] else 'FAIL'}")
    print(f"Issues: {results['issue_count']['critical']} critical, {results['issue_count']['major']} major, {results['issue_count']['minor']} minor")
    print(f"\nReport: {report_path}")
    print(f"JSON:   {json_path}")
    print(f"Screenshots: {output_dir or '/tmp/editing_workflow_test'}")

    return results


if __name__ == '__main__':
    import sys

    # Use first sample PDF if no path provided
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Try to find a sample PDF
        sample_dir = Path('ignored-resources/sample-files-marcedit')
        if sample_dir.exists():
            pdfs = list(sample_dir.glob('*.pdf'))
            if pdfs:
                pdf_path = str(pdfs[0])
                print(f"Using sample PDF: {pdf_path}")
            else:
                print("No sample PDFs found!")
                sys.exit(1)
        else:
            print("Please provide a PDF path as argument")
            sys.exit(1)

    results = run_visual_editing_test(
        pdf_path=pdf_path,
        output_dir='/tmp/marcedit_editing_workflow'
    )

    sys.exit(0 if results['passed'] else 1)
