#!/bin/bash
#
# UI Test Runner for Marcedit
# Runs GUI tests using Python harness (no Xcode required)
#
# Usage:
#   ./scripts/run-ui-tests.sh              # Run all tests
#   ./scripts/run-ui-tests.sh --test zoom  # Run tests matching "zoom"
#   ./scripts/run-ui-tests.sh --verbose    # Verbose output
#   ./scripts/run-ui-tests.sh --keep       # Keep app running after tests
#
# Options:
#   --test, -t FILTER   Run only tests matching FILTER
#   --verbose, -v       Show verbose debug output
#   --keep, -k          Don't quit app after tests
#   --no-build          Skip building the app
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=================================="
echo "Marcedit UI Test Runner"
echo "=================================="
echo "Project: $PROJECT_DIR"
echo ""

# Parse arguments
ARGS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --test|-t)
            ARGS="$ARGS --test $2"
            shift 2
            ;;
        --verbose|-v)
            ARGS="$ARGS --verbose"
            shift
            ;;
        --keep|-k)
            ARGS="$ARGS --keep-running"
            shift
            ;;
        --no-build)
            ARGS="$ARGS --no-build"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run Python GUI tests
cd "$PROJECT_DIR"
python3 tests/gui_harness/run_gui_tests.py $ARGS
