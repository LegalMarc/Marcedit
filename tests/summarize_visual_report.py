#!/usr/bin/env python3
"""
summarize_visual_report.py — text-based summary of visual test results.

Reads results from both the Python visual harness and XCUITest visual report,
and prints a concise, LLM-readable summary to stdout.

Output includes:
  - Per-PDF pass/fail counts
  - List of all failures with target text, error message, and file paths
  - List of all successful edits with before/after PNG paths for visual inspection
  - Overall statistics

This is designed for Claude Code to read and act on — the paths to PNG files
can be passed to the Read tool for visual inspection.
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Python visual harness results ─────────────────────────────────────────────

PYTHON_RESULTS = PROJECT_ROOT / "tests" / "visual_edit_harness_report" / "results.json"
PYTHON_REPORT_DIR = PROJECT_ROOT / "tests" / "visual_edit_harness_report"

# ── XCUITest visual report results ────────────────────────────────────────────

XCUI_RESULTS = Path("/tmp/marcedit_visual_report/visual_report.json")
XCUI_REPORT_DIR = Path("/tmp/marcedit_visual_report")


def summarize_python_harness():
    """Summarize the Python visual edit harness results."""
    if not PYTHON_RESULTS.exists():
        print("  [not found] No Python harness results at:")
        print(f"    {PYTHON_RESULTS}")
        print("  Run: python3 tests/visual_edit_harness.py")
        return

    data = json.loads(PYTHON_RESULTS.read_text())
    total_ok = sum(r["summary"]["success"] for r in data)
    total_fail = sum(r["summary"]["failed"] for r in data)
    total_skip = sum(r["summary"]["skipped"] for r in data)
    total = total_ok + total_fail + total_skip

    print(f"  Total edits: {total}  |  OK: {total_ok}  |  FAIL: {total_fail}  |  SKIP: {total_skip}")
    pct = 100 * total_ok // max(total_ok + total_fail, 1)
    print(f"  Success rate: {pct}%")
    print()

    # Per-PDF summary
    print("  Per-PDF breakdown:")
    for r in data:
        ok = r["summary"]["success"]
        fail = r["summary"]["failed"]
        marker = "PASS" if fail == 0 else "FAIL"
        print(f"    [{marker}] {r['pdf'][:50]:50s}  ok={ok}  fail={fail}")

    # Failures detail
    failures = []
    for r in data:
        for e in r["edits"]:
            if e["status"] != "success":
                failures.append((r["pdf"], e))

    if failures:
        print()
        print(f"  ── {len(failures)} Failure(s) ──")
        for pdf, e in failures:
            print(f"    {pdf[:40]}  p{e['page']}")
            print(f"      target:  {e['target'][:60]}")
            print(f"      replace: {e['replacement'][:60]}")
            print(f"      error:   {e['message'][:100]}")
            if e.get("debug_log"):
                print(f"      debug:   {e['debug_log'][-1][:100]}")

    # Successful edits with PNG paths for visual inspection
    successes = []
    for r in data:
        for e in r["edits"]:
            if e["status"] == "success":
                successes.append((r["pdf"], e))

    if successes:
        print()
        print(f"  ── {len(successes)} Successful Edit(s) — PNG paths for visual inspection ──")
        for pdf, e in successes[:10]:  # show first 10
            print(f"    {pdf[:40]}  p{e['page']}  edit_{e['index']:02d}")
            print(f"      target:  {e['target'][:50]}")
            print(f"      replace: {e['replacement'][:50]}")
            if e.get("crop_before_png"):
                print(f"      crop_before: {e['crop_before_png']}")
                print(f"      crop_after:  {e['crop_after_png']}")
            else:
                print(f"      before: {e['before_png']}")
                print(f"      after:  {e['after_png']}")
        if len(successes) > 10:
            print(f"    ... and {len(successes) - 10} more (see results.json)")


def summarize_xcui_report():
    """Summarize the XCUITest visual report results."""
    if not XCUI_RESULTS.exists():
        print("  [not found] No XCUITest visual report at:")
        print(f"    {XCUI_RESULTS}")
        print("  Run: tests/run_visual_tests.sh xcui")
        return

    data = json.loads(XCUI_RESULTS.read_text())
    total = len(data)
    ok = sum(1 for e in data if e["status"] == "success")
    fail = sum(1 for e in data if e["status"] == "failed")
    skip = sum(1 for e in data if e["status"] == "skipped")

    print(f"  Total cases: {total}  |  OK: {ok}  |  FAIL: {fail}  |  SKIP: {skip}")
    print()

    for e in data:
        marker = "PASS" if e["status"] == "success" else "FAIL"
        bbox_str = f"  diff={e['diffBBox']}" if e.get("diffBBox") else ""
        print(f"    [{marker}] {e['caseID']:30s}  page {e['page']}{bbox_str}")
        print(f"      {e['targetText'][:50]} -> {e['replacement'][:50]}")
        if e.get("cropBeforePNG"):
            print(f"      crop_before: {e['cropBeforePNG']}")
            print(f"      crop_after:  {e['cropAfterPNG']}")
        elif e.get("beforePNG"):
            print(f"      before: {e['beforePNG']}")
            print(f"      after:  {e['afterPNG']}")
        if e["status"] == "failed" and e.get("message"):
            print(f"      error: {e['message'][:100]}")


def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║           Marcedit Visual Test Summary                       ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()

    print("┌─── Python Visual Edit Harness ────────────────────────────────")
    summarize_python_harness()
    print()

    print("┌─── XCUITest Visual Report ────────────────────────────────────")
    summarize_xcui_report()
    print()

    # Final instructions for the LLM
    print("┌─── Next Steps ────────────────────────────────────────────────")
    print("  To visually inspect an edit, use the Read tool on the PNG paths above.")
    print("  Crop images show just the changed region — check for:")
    print("    - Text rendered correctly (no garbled characters)")
    print("    - Font matches original (same weight, style, size)")
    print("    - No visual collisions with surrounding content")
    print("    - Proper alignment and positioning")
    print()
    print("  To fix issues:")
    print("    1. Identify the failure from the summary above")
    print("    2. Read the relevant source in Sources/Marcedit/python_site/editor_pkg/")
    print("    3. Fix the code")
    print("    4. Re-run: tests/run_visual_tests.sh python")
    print("    5. Check the summary again")


if __name__ == "__main__":
    main()
