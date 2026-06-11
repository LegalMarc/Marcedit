#!/bin/bash
#
# build-and-test-ui.sh
# Build the app and run XCUITests
#
# Usage:
#   ./Scripts/build-and-test-ui.sh          # Run all UI tests
#   ./Scripts/build-and-test-ui.sh TestName # Run specific test
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Building Marcedit ==="
cd "$PROJECT_DIR"
swift build -c release

APP_PATH="$PROJECT_DIR/.build/release/Marcedit.app"

# Check if app exists
if [ ! -d "$APP_PATH" ]; then
    echo "Error: App not found at $APP_PATH"
    echo "Make sure swift build created the app bundle"
    exit 1
fi

echo "=== App built at: $APP_PATH ==="

# Check if XCUITest project exists
UITEST_PROJECT="$PROJECT_DIR/MarceditUITests/MarceditUITests.xcodeproj"

if [ ! -d "$UITEST_PROJECT" ]; then
    echo ""
    echo "XCUITest project not found at: $UITEST_PROJECT"
    echo ""
    echo "To create the XCUITest project:"
    echo "1. Open Xcode"
    echo "2. File > New > Project"
    echo "3. Choose macOS > Test > UI Testing Bundle"
    echo "4. Set Product Name to 'MarceditUITestsUITests'"
    echo "5. Save to $PROJECT_DIR/MarceditUITests/"
    echo "6. Add the test files from MarceditUITestsUITests/ to the target"
    echo "7. Set the Target Application to the built Marcedit.app"
    echo ""
    echo "Alternatively, run the Python harness:"
    echo "  python3 tests/visual_harness/run_tests.py"
    exit 1
fi

echo "=== Running UI Tests ==="

# Build arguments for xcodebuild
XCODE_ARGS=(
    "-project" "$UITEST_PROJECT"
    "-scheme" "MarceditUITestsUITests"
    "-destination" "platform=macOS"
)

# If a test name was provided, run only that test
if [ -n "$1" ]; then
    XCODE_ARGS+=("-only-testing:MarceditUITestsUITests/$1")
fi

# Run tests
xcodebuild test "${XCODE_ARGS[@]}"

echo "=== UI Tests Complete ==="
