#!/bin/bash
# Diagnostic script for Marcedit build issues

echo "========================================"
echo "Marcedit Build Diagnostics"
echo "========================================"
echo ""

PROJECT_ROOT="."
BUILD_DIR="$PROJECT_ROOT/ignored-resources"
APP_BUNDLE="$BUILD_DIR/Marcedit.app"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# 1. Check if app bundle exists
echo "1. Checking App Bundle Structure..."
if [ -d "$APP_BUNDLE" ]; then
    check_pass "App bundle exists at $APP_BUNDLE"
else
    check_fail "App bundle not found at $APP_BUNDLE"
    echo "   Run: python3 build_tui.py (Option 1 or 2)"
    exit 1
fi

# 2. Check Contents directory structure
echo ""
echo "2. Checking Directory Structure..."
if [ -d "$APP_BUNDLE/Contents" ]; then
    check_pass "Contents directory exists"
else
    check_fail "Contents directory missing"
fi

if [ -d "$APP_BUNDLE/Contents/MacOS" ]; then
    check_pass "MacOS directory exists"
else
    check_fail "MacOS directory missing"
fi

if [ -d "$APP_BUNDLE/Contents/Resources" ]; then
    check_pass "Resources directory exists"
else
    check_fail "Resources directory missing"
fi

# 3. Check binary
echo ""
echo "3. Checking Binary..."
if [ -f "$APP_BUNDLE/Contents/MacOS/Marcedit" ]; then
    check_pass "Binary exists"

    # Check if binary is executable
    if [ -x "$APP_BUNDLE/Contents/MacOS/Marcedit" ]; then
        check_pass "Binary is executable"
    else
        check_fail "Binary is not executable"
        chmod +x "$APP_BUNDLE/Contents/MacOS/Marcedit"
    fi

    # Check binary architecture
    echo "   Architecture: $(file "$APP_BUNDLE/Contents/MacOS/Marcedit" | cut -d: -f2)"
else
    check_fail "Binary not found"
fi

# 4. Check Info.plist
echo ""
echo "4. Checking Info.plist..."
if [ -f "$APP_BUNDLE/Contents/Info.plist" ]; then
    check_pass "Info.plist exists"

    # Check if Info.plist is valid
    if /usr/libexec/PlistBuddy -c print "$APP_BUNDLE/Contents/Info.plist" > /dev/null 2>&1; then
        check_pass "Info.plist is valid"

        # Display key info
        echo "   Version: $(/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || echo "N/A")"
        echo "   Build: $(/usr/libexec/PlistBuddy -c "Print CFBundleVersion" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || echo "N/A")"
        echo "   Min OS: $(/usr/libexec/PlistBuddy -c "Print LSMinimumSystemVersion" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || echo "N/A")"
    else
        check_fail "Info.plist is invalid"
    fi
else
    check_fail "Info.plist not found"
fi

# 5. Check Assets.car
echo ""
echo "5. Checking Assets.car..."
if [ -f "$APP_BUNDLE/Contents/Resources/Assets.car" ]; then
    check_pass "Assets.car exists"
    SIZE=$(du -h "$APP_BUNDLE/Contents/Resources/Assets.car" | cut -f1)
    echo "   Size: $SIZE"
else
    check_warn "Assets.car not found (may cause UI issues)"
fi

# 6. Check AppIcon.icns
echo ""
echo "6. Checking AppIcon.icns..."
if [ -f "$APP_BUNDLE/Contents/Resources/AppIcon.icns" ]; then
    check_pass "AppIcon.icns exists"
else
    check_warn "AppIcon.icns not found (may cause icon issues)"
fi

# 7. Check code signature
echo ""
echo "7. Checking Code Signature..."
if codesign -dv "$APP_BUNDLE" 2>&1 | grep -q "valid on disk"; then
    check_pass "App is properly signed"
else
    check_warn "Code signature issues detected"
    echo "   Attempting to re-sign..."
    codesign --force --sign - "$APP_BUNDLE" 2>&1
fi

# 8. Check resource bundle
echo ""
echo "8. Checking Resource Bundle..."
RESOURCE_BUNDLE="$APP_BUNDLE/Contents/Resources/Marcedit_Marcedit.bundle"
if [ -d "$RESOURCE_BUNDLE" ]; then
    check_pass "Resource bundle exists"

    # Check for fonts
    if [ -d "$RESOURCE_BUNDLE/fonts" ]; then
        FONT_COUNT=$(ls -1 "$RESOURCE_BUNDLE/fonts" 2>/dev/null | wc -l)
        check_pass "Fonts directory exists ($FONT_COUNT fonts)"
    else
        check_warn "Fonts directory not found in resource bundle"
    fi
else
    check_warn "Resource bundle not found"
fi

# 9. Check for embedded Python
echo ""
echo "9. Checking Embedded Python..."
PYTHON_BUNDLE="$APP_BUNDLE/Contents/Resources/python"
if [ -d "$PYTHON_BUNDLE" ]; then
    check_pass "Python bundle found"

    if [ -f "$PYTHON_BUNDLE/bin/python3" ]; then
        check_pass "Python3 binary exists"

        # Check Python version
        PYTHON_VERSION=$("$PYTHON_BUNDLE/bin/python3" --version 2>&1 || echo "N/A")
        echo "   Version: $PYTHON_VERSION"
    else
        check_warn "Python3 binary not found"
    fi
else
    check_warn "Python bundle not found (expected for Release builds)"
fi

# 10. Check for crash logs
echo ""
echo "10. Checking for Recent Crash Logs..."
CRASH_DIR="$HOME/Library/Logs/DiagnosticReports"
RECENT_CRASH=$(ls -t "$CRASH_DIR"/Marcedit*.crash 2>/dev/null | head -1)

if [ -n "$RECENT_CRASH" ]; then
    check_warn "Recent crash log found"
    echo "   Location: $RECENT_CRASH"
    echo "   Time: $(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$RECENT_CRASH" 2>/dev/null || stat -c "%y" "$RECENT_CRASH" 2>/dev/null | cut -d. -f1)"

    # Show crash reason
    CRASH_REASON=$(grep "Exception Type:" "$RECENT_CRASH" | head -1)
    if [ -n "$CRASH_REASON" ]; then
        echo "   $CRASH_REASON"
    fi
else
    check_pass "No recent crash logs found"
fi

# 11. Try to launch app in background and check logs
echo ""
echo "11. Attempting Background Launch Test..."
echo "   (This will launch the app briefly to capture any startup errors)"

# Launch in background
OUTPUT=$(("$APP_BUNDLE/Contents/MacOS/Marcedit" 2>&1) &)
APP_PID=$!

# Wait briefly and check
sleep 2

# Check if process is still running
if ps -p $APP_PID > /dev/null 2>&1; then
    check_pass "App launched successfully (PID: $APP_PID)"
    echo "   Killing test process..."
    kill $APP_PID 2>/dev/null
else
    check_fail "App crashed or exited immediately"
    if [ -n "$OUTPUT" ]; then
        echo "   Error output:"
        echo "$OUTPUT" | head -20
    fi
fi

# Summary
echo ""
echo "========================================"
echo "Diagnostic Summary"
echo "========================================"

# Provide recommendations
echo ""
echo "Recommendations:"

if [ ! -f "$APP_BUNDLE/Contents/Resources/Assets.car" ]; then
    echo "  - Rebuild app to generate Assets.car"
    echo "  - Check that Assets.xcassets exists in Sources/Marcedit/"
fi

if [ ! -f "$APP_BUNDLE/Contents/Resources/AppIcon.icns" ]; then
    echo "  - Rebuild app to generate AppIcon.icns"
    echo "  - Check that AppIcon.appiconset exists"
fi

if [ -n "$RECENT_CRASH" ]; then
    echo ""
    echo "CRASH ANALYSIS:"
    echo "  Most recent crash: $RECENT_CRASH"
    echo ""
    echo "  First few lines of crash log:"
    head -30 "$RECENT_CRASH"
fi

echo ""
echo "For detailed crash analysis, run:"
echo "  open $RECENT_CRASH"
echo ""
echo "To clean and rebuild:"
echo "  python3 build_tui.py"
echo "  Select option 6 (Clean Build Directory)"
echo "  Then select option 2 (Build Release)"
echo ""
