#!/usr/bin/env bash
# run_visual_tests.sh — unified runner for Marcedit visual verification
#
# Modes:
#   ./tests/run_visual_tests.sh python     Run Python visual edit harness (headless, no GUI)
#   ./tests/run_visual_tests.sh xcui       Run XCUITest visual report (requires display)
#   ./tests/run_visual_tests.sh all        Run both
#   ./tests/run_visual_tests.sh summary    Just print summary of last run (no re-run)
#
# Output:
#   Python harness  → tests/visual_edit_harness_report/  (report.html, results.json)
#   XCUITest report → /tmp/marcedit_visual_report/       (visual_report.html, visual_report.json)
#   Text summary    → stdout (always printed after any run)

set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

MODE="${1:-python}"

# ── Python visual edit harness ────────────────────────────────────────────────

run_python_harness() {
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Running Python visual edit harness (headless)"
    echo "═══════════════════════════════════════════════════════════════"

    if [ ! -d "ignored-resources/sample-files-marcedit" ]; then
        echo "ERROR: No sample PDFs found at ignored-resources/sample-files-marcedit/"
        echo "       Place real-world PDFs there to run the visual harness."
        return 1
    fi

    python3 tests/visual_edit_harness.py

    echo ""
    echo "── Python harness complete ──"
    echo "   Report: tests/visual_edit_harness_report/report.html"
    echo "   JSON:   tests/visual_edit_harness_report/results.json"
}

# ── XCUITest visual report ────────────────────────────────────────────────────

run_xcui_tests() {
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Running XCUITest visual report (requires display)"
    echo "═══════════════════════════════════════════════════════════════"

    # Ensure corpus exists
    if [ ! -d "tests/ui_corpus/cases" ] || [ -z "$(ls tests/ui_corpus/cases/ 2>/dev/null)" ]; then
        echo "  Generating test corpus..."
        python3 tests/ui_corpus/generate_corpus.py
    fi

    # Clean stale UI-test outputs before copying the shared corpus.
    tmp_root="${TMPDIR:-/tmp/}"
    rm -rf /tmp/marcedit_uitest_[0-9]* "$tmp_root"/marcedit_uitest_[0-9]* /tmp/marcedit_visual_report
    python3 - <<'PY'
from pathlib import Path
import shutil

home = Path.home()
roots = [home / "Library" / "Caches" / "MarceditUITests"]
roots.extend((home / "Library" / "Containers").glob("*/Data/Library/Caches/MarceditUITests"))
for root in roots:
    if root.exists():
        for child in root.glob("marcedit_uitest_*"):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
PY

    # Copy corpus to /tmp for test runner
    rm -rf /tmp/marcedit_uitest_corpus
    cp -R tests/ui_corpus/cases /tmp/marcedit_uitest_corpus
    echo "  Corpus copied to /tmp/marcedit_uitest_corpus"

    # Build + run visual report test only
    echo "  Building and running testVisualReport_AllCases..."
    pkill -f 'Marcedit.app/Contents/MacOS/Marcedit' 2>/dev/null || true
    mkdir -p tests/visual_harness/diagnostic_output
    xcui_log="tests/visual_harness/diagnostic_output/xcui_visual_report.log"
    export MARCEDIT_XCUI_CASE_ROOT="$tmp_root"
    set +e
    python3 tests/run_with_timeout.py \
        --timeout 600 \
        --log "$xcui_log" \
        -- \
        xcodebuild test \
            -scheme MarceditUITests \
            -destination 'platform=macOS' \
            -only-testing:"MarceditUITests/RealWorldEditTests/testVisualReport_AllCases" \
        | tail -40
    xcui_status=${PIPESTATUS[0]}
    set -e

    render_status=0
    python3 tests/render_xcui_visual_report.py || render_status=$?

    echo ""
    echo "── XCUITest visual report complete ──"
    echo "   Report: /tmp/marcedit_visual_report/visual_report.html"
    echo "   JSON:   /tmp/marcedit_visual_report/visual_report.json"

    if [ "$xcui_status" -ne 0 ]; then
        return "$xcui_status"
    fi
    if [ "$render_status" -ne 0 ]; then
        return "$render_status"
    fi
}

# ── Summary ───────────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Visual Test Summary"
    echo "═══════════════════════════════════════════════════════════════"
    python3 tests/summarize_visual_report.py
}

# ── Main ──────────────────────────────────────────────────────────────────────

case "$MODE" in
    python)
        run_python_harness
        print_summary
        ;;
    xcui)
        run_xcui_tests
        print_summary
        ;;
    all)
        run_python_harness
        run_xcui_tests
        print_summary
        ;;
    summary)
        print_summary
        ;;
    *)
        echo "Usage: $0 {python|xcui|all|summary}"
        exit 1
        ;;
esac
