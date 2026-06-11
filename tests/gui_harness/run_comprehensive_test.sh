#!/bin/bash
#
# Run comprehensive GUI test suite for Marcedit
#
# Usage:
#   ./run_comprehensive_test.sh [pdf_path] [--category name]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🎯 Marcedit Comprehensive GUI Test Runner"
echo "=========================================="
echo ""

# Check if Marcedit is running
if ! pgrep -x "Marcedit" > /dev/null; then
    echo "⚠️  WARNING: Marcedit is not running"
    echo "   Please launch Marcedit first"
    echo ""
    read -p "Press Enter after launching Marcedit..."
fi

# Check for Python dependencies
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "⚠️  WARNING: PIL (Pillow) not found"
    echo "   Installing required dependencies..."
    pip3 install Pillow pytesseract
fi

# Run tests
cd "$PROJECT_ROOT"
python3 -m tests.gui_harness.comprehensive_gui_test "$@"

exit $?
