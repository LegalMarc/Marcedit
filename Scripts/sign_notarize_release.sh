#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DERIVED_DATA="${DERIVED_DATA:-$ROOT/build/DerivedData-DeveloperID}"
APP="$DERIVED_DATA/Build/Products/Release/Marcedit.app"
ZIP_DIR="$ROOT/build/notarization"
ZIP="$ZIP_DIR/Marcedit-DeveloperID.zip"
IDENTITY="${DEVELOPER_ID_IDENTITY:-Developer ID Application: Marc Mandel (QG85EMCQ75)}"
TEAM_ID="${DEVELOPMENT_TEAM_ID:-QG85EMCQ75}"
NOTARY_PROFILE="${NOTARY_PROFILE:-marcedit-public-beta}"
ENTITLEMENTS="$ROOT/Sources/Marcedit/Marcedit.entitlements"

cd "$ROOT"

xcodebuild build \
  -scheme MarceditUITests \
  -configuration Release \
  -destination 'platform=macOS' \
  -derivedDataPath "$DERIVED_DATA" \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGN_IDENTITY="$IDENTITY" \
  DEVELOPMENT_TEAM="$TEAM_ID" \
  PROVISIONING_PROFILE_SPECIFIER= \
  -quiet

find "$APP" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$APP" -name '.DS_Store' -type f -delete

while IFS= read -r -d '' file; do
  if file -b "$file" | grep -q 'Mach-O'; then
    codesign --force --sign "$IDENTITY" --options runtime --timestamp "$file"
  fi
done < <(find "$APP" -type f -print0)

find "$APP" \( -name '*.app' -o -name '*.framework' \) -type d -print | sort -r | while IFS= read -r bundle; do
  codesign --force --sign "$IDENTITY" --options runtime --timestamp "$bundle"
done

codesign --force --sign "$IDENTITY" --options runtime --timestamp --entitlements "$ENTITLEMENTS" "$APP"
python3 Scripts/verify_release_security.py --app "$APP" --require-developer-id

rm -rf "$ZIP_DIR"
mkdir -p "$ZIP_DIR"
/usr/bin/ditto -c -k --keepParent "$APP" "$ZIP"

xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute --verbose=4 "$APP"
python3 Scripts/verify_release_security.py --app "$APP" --require-developer-id

rm -f "$ZIP"
/usr/bin/ditto -c -k --keepParent "$APP" "$ZIP"

printf 'Notarized app: %s\n' "$APP"
printf 'Notarized zip: %s\n' "$ZIP"
