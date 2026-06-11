#!/bin/bash
set -e

echo "🔨 Building Marcedit DMG..."

# Extract version from version.json
MAJOR=$(grep '"major"' version.json | sed 's/.*: *\([0-9]*\).*/\1/')
MINOR=$(grep '"minor"' version.json | sed 's/.*: *\([0-9]*\).*/\1/')
PATCH=$(grep '"patch"' version.json | sed 's/.*: *\([0-9]*\).*/\1/')
VERSION="${MAJOR}.${MINOR}.${PATCH}"

# Configuration
APP_NAME="Marcedit"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
BUILD_DIR=".build"
RELEASE_DIR="release"
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"
DMG_PATH="${RELEASE_DIR}/${DMG_NAME}"

echo "📦 Version: ${VERSION}"

# Create release directory
mkdir -p "${RELEASE_DIR}"

# Step 1: Build the app (if needed or --rebuild flag)
if [ ! -f "${BUILD_DIR}/apple/Products/Release/${APP_NAME}" ] || [ "${1}" == "--rebuild" ]; then
    echo "⚙️  Building ${APP_NAME} in Release mode..."
    swift build -c release
else
    echo "✅ Using existing build"
fi

# Step 2: Create Info.plist if missing
if [ ! -f "${APP_BUNDLE}/Contents/Info.plist" ]; then
    echo "📝 Creating Info.plist..."
    cat > "${APP_BUNDLE}/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>Marcedit</string>
    <key>CFBundleIdentifier</key>
    <string>com.marclaw.Marcedit</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Marcedit</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>VERSION_PLACEHOLDER</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>pdf</string>
            </array>
            <key>CFBundleTypeName</key>
            <string>PDF Document</string>
            <key>CFBundleTypeRole</key>
            <string>Editor</string>
            <key>LSHandlerRank</key>
            <string>Default</string>
        </dict>
    </array>
</dict>
</plist>
EOF
    sed -i '' "s/VERSION_PLACEHOLDER/${VERSION}/g" "${APP_BUNDLE}/Contents/Info.plist"
fi

# Step 3: Assemble app bundle
echo "📦 Assembling app bundle..."

# Copy executable
echo "  → Copying executable..."
cp "${BUILD_DIR}/apple/Products/Release/${APP_NAME}" "${APP_BUNDLE}/Contents/MacOS/"

# Copy resource bundle
if [ -d "${BUILD_DIR}/apple/Products/Release/${APP_NAME}_${APP_NAME}.bundle" ]; then
    echo "  → Copying resource bundle..."
    cp -R "${BUILD_DIR}/apple/Products/Release/${APP_NAME}_${APP_NAME}.bundle" "${APP_BUNDLE}/Contents/Resources/" 2>/dev/null || true
fi

# Copy Python resources
if [ -d "Sources/${APP_NAME}/python_site" ]; then
    echo "  → Copying Python resources..."
    cp -R "Sources/${APP_NAME}/python_site" "${APP_BUNDLE}/Contents/Resources/"
fi

APP_SIZE=$(du -sh "${APP_BUNDLE}" | cut -f1)
echo "  → App bundle size: ${APP_SIZE}"

# Step 4: Create DMG
echo "💿 Creating DMG..."

# Remove old DMG
rm -f "${DMG_PATH}"

# Create temporary DMG directory
TMP_DMG_DIR="${BUILD_DIR}/dmg_temp"
rm -rf "${TMP_DMG_DIR}"
mkdir -p "${TMP_DMG_DIR}"

# Copy app to temp directory
cp -R "${APP_BUNDLE}" "${TMP_DMG_DIR}/"

# Create Applications symlink
ln -s /Applications "${TMP_DMG_DIR}/Applications"

# Create README
cat > "${TMP_DMG_DIR}/README.txt" << EOFREADME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Marcedit - PDF Text Editor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INSTALLATION:
1. Drag Marcedit.app to Applications
2. Open from Applications
3. Start editing PDFs!

REQUIREMENTS:
• macOS 13.0+ (Ventura or later)
• Apple Silicon or Intel Mac

FEATURES:
✨ In-place PDF text editing
✨ Font matching & synthesis
✨ Multi-line text reflow
✨ Visual preview mode
✨ Block editing with styles
✨ Production-ready quality

SUPPORT:
github.com/yourusername/marcedit

Version: ${VERSION}
Built: $(date '+%B %Y')
EOFREADME

# Create the DMG
hdiutil create -volname "${APP_NAME} ${VERSION}" \
    -srcfolder "${TMP_DMG_DIR}" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "${DMG_PATH}" > /dev/null

# Cleanup
rm -rf "${TMP_DMG_DIR}"

# Get DMG info
DMG_SIZE=$(du -h "${DMG_PATH}" | cut -f1)

# Success message
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Marcedit DMG created successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 File: ${DMG_NAME}"
echo "📍 Location: ${RELEASE_DIR}/"
echo "📏 Compressed: ${DMG_SIZE}"
echo "💾 Uncompressed: ${APP_SIZE}"
echo "🔖 Version: ${VERSION}"
echo ""
echo "To install:"
echo "  1. Double-click ${DMG_NAME}"
echo "  2. Drag Marcedit to Applications"
echo "  3. Launch from Applications!"
echo ""
echo "To distribute:"
echo "  Share ${RELEASE_DIR}/${DMG_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Open release folder
if command -v open &> /dev/null; then
    open "${RELEASE_DIR}"
fi
