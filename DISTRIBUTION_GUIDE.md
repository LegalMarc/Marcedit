# Marcedit Distribution Guide

Quick reference for distributing Marcedit using the enhanced build_tui.py.

---

## Quick Start: Create a DMG

```bash
./build_tui.py
# Select option 23: Create DMG Installer
```

**Output:** `release/Marcedit-{version}.dmg`

---

## Complete Release Process

### One-Command Release (Recommended)

```bash
./build_tui.py
# Select option 27: Complete Release Workflow
```

This will:
1. ✓ Clean existing builds
2. ✓ Build fresh Release configuration
3. ✓ Run all unit tests
4. ✓ Create DMG installer
5. ✓ Optionally sign with Developer ID
6. ✓ Optionally notarize with Apple

---

## Step-by-Step Release Process

### 1. Clean Build
```bash
./build_tui.py
# Select option 28: Clean Build (Full Rebuild)
```

### 2. Build Release
```bash
./build_tui.py
# Select option 2: Build Release
```

### 3. Run Tests
```bash
./build_tui.py
# Select option 8: Run pytest (All Tests)
```

### 4. Create DMG
```bash
./build_tui.py
# Select option 23: Create DMG Installer
```

### 5. Sign (Optional)
```bash
./build_tui.py
# Select option 24: Sign for Distribution (Developer ID)
# Enter your Developer ID Application identity
```

### 6. Notarize (Optional)
```bash
./build_tui.py
# Select option 25: Notarize with Apple
# Enter Apple ID email and Team ID
```

---

## Distribution Scenarios

### Scenario 1: Internal Testing
**Goal:** Quick DMG for testing on other machines

**Steps:**
1. Build Release (option 2)
2. Create DMG (option 23)

**Result:** Unsigned DMG - users will see Gatekeeper warnings

---

### Scenario 2: Beta Distribution
**Goal:** Signed DMG for beta testers

**Steps:**
1. Complete Release Workflow (option 27)
2. Sign when prompted
3. Skip notarization

**Result:** Signed DMG - reduced warnings, not notarized

---

### Scenario 3: Public Release
**Goal:** Professional distribution ready for download

**Steps:**
1. Complete Release Workflow (option 27)
2. Sign when prompted
3. Notarize when prompted

**Result:** Signed & notarized DMG - no warnings, professional quality

---

### Scenario 4: App Store Release
**Goal:** Submit to Mac App Store

**Steps:**
1. Build with Mac App Store provisioning profile (manual)
2. Archive with Xcode (Product > Archive)
3. Upload via Xcode Organizer or Transporter

**Note:** Option 26 provides guidance but requires Xcode workflow

---

## Troubleshooting

### DMG Creation Fails

**Problem:** "App bundle not found"
**Solution:**
```bash
./build_tui.py
# Option 2: Build Release
# Option 23: Create DMG Installer
```

**Problem:** "hdiutil: create failed"
**Solution:** Check disk space, ensure no DMG is mounted

---

### Code Signing Issues

**Problem:** "No Developer ID certificate found"
**Solution:**
1. Join Apple Developer Program ($99/year)
2. Visit developer.apple.com/account/resources/certificates
3. Create "Developer ID Application" certificate
4. Download and install in Keychain

**Problem:** "codesign failed - errSecInternalComponent"
**Solution:**
```bash
# Unlock keychain
security unlock-keychain ~/Library/Keychains/login.keychain-db
# Try signing again
```

---

### Notarization Issues

**Problem:** "Error: Unable to authenticate"
**Solution:**
1. Create app-specific password at appleid.apple.com
2. Use app-specific password (not Apple ID password)

**Problem:** "Notarization failed - invalid signing"
**Solution:**
- Ensure app is signed with Developer ID first (option 24)
- Check that hardened runtime is enabled

**Problem:** "Notarization in progress for a long time"
**Solution:**
- Notarization can take 5-30 minutes
- Use `--wait` flag (already included)
- Check status: `xcrun notarytool history --apple-id {email} --team-id {team}`

---

## Version Management

### Version Numbers
Stored in `version.json`:
```json
{
  "major": 0,
  "minor": 6,
  "patch": 91
}
```

### Automatic Incrementing
- Patch number auto-increments on each build
- Manual editing for major/minor versions

### DMG Naming
Format: `Marcedit-{major}.{minor}.{patch}.dmg`
Example: `Marcedit-0.6.91.dmg`

---

## Certificate Requirements

### Developer ID Distribution

**What you need:**
1. Apple Developer Account ($99/year)
2. Developer ID Application certificate
3. Installed in Keychain

**How to get it:**
```
1. Log in to developer.apple.com
2. Go to Certificates, Identifiers & Profiles
3. Create Certificate > Developer ID > Developer ID Application
4. Download certificate
5. Double-click to install in Keychain
```

**Verify installation:**
```bash
security find-identity -v -p codesigning
# Should show "Developer ID Application: Your Name (TEAMID)"
```

---

### Mac App Store Distribution

**What you need:**
1. Mac App Store distribution certificate
2. App Store provisioning profile
3. App registered in App Store Connect

**Note:** Not yet automated in build_tui.py - use Xcode workflow

---

## Checklist: Before Public Release

### Pre-Build
- [ ] Update version in version.json (major/minor if needed)
- [ ] Update CHANGELOG.md with new features
- [ ] Run full test suite (option 8)
- [ ] Fix any failing tests
- [ ] Update README.md if needed

### Build & Test
- [ ] Clean build (option 28)
- [ ] Build Release (option 2)
- [ ] Run pytest (option 8)
- [ ] Run GUI tests (option 20)
- [ ] Manual smoke test

### Distribution
- [ ] Create DMG (option 23)
- [ ] Sign with Developer ID (option 24)
- [ ] Notarize with Apple (option 25)
- [ ] Test DMG installation on clean system

### Release
- [ ] Upload DMG to GitHub releases
- [ ] Update website/download links
- [ ] Announce on social media/blog
- [ ] Monitor for crash reports

---

## File Locations

### Build Outputs
- **App Bundle:** `ignored-resources/Marcedit.app`
- **SwiftPM Cache:** `.build/`

### Distribution Outputs
- **DMG Installers:** `release/Marcedit-*.dmg`
- **Version File:** `version.json`

### Test Outputs
- **Test Reports:** `tests/`
- **Coverage:** `htmlcov/`

---

## Command Reference

### TUI Menu Options

**Building:**
- 1: Build Debug
- 2: Build Release
- 3: Build & Run (Debug)
- 5: Clean Build Directory
- 28: Clean Build (Full Rebuild)

**Testing:**
- 7: SwiftPM Tests
- 8: pytest (All Tests)
- 12: Pipeline Verification
- 20: GUI Tests (All)

**Distribution:**
- 23: Create DMG Installer
- 24: Sign for Distribution
- 25: Notarize with Apple
- 27: Complete Release Workflow

---

## Security Notes

### Code Signing Best Practices
- Never share your signing certificate
- Keep private key secure in Keychain
- Use app-specific passwords (not main Apple ID password)
- Enable two-factor authentication on Apple ID

### Notarization
- Required for macOS 10.15+ (Catalina and later)
- Users on older macOS can still run unsigned apps
- Notarization is separate from App Store review

### Gatekeeper
- Unsigned apps: "App cannot be opened" error
- Signed apps: Warning about unknown developer
- Signed + notarized: No warnings

---

## Tips & Tricks

### Faster Iteration
For testing DMG creation without full rebuild:
```bash
./build_tui.py
# Option 23 only (uses existing build)
```

### Test Installation
```bash
# Mount DMG
open release/Marcedit-*.dmg
# Drag to /Applications
# Test launch
```

### Verify Signing
```bash
codesign -dvvv ignored-resources/Marcedit.app
# Should show Developer ID signature

spctl -a -vv ignored-resources/Marcedit.app
# Should show "accepted" if signed+notarized
```

### Check Notarization Status
```bash
xcrun notarytool history --apple-id your@email.com --team-id TEAMID
```

---

## Support

### Documentation
- Build system: BUILD_TUI_ENHANCEMENTS.md
- Bug fixes: COMPLETE_BUG_FIX_SUMMARY.md
- Implementation plan: PLAN-gui-automation.md

### Common Issues
- Build errors: Check Swift version (macOS 14.0+)
- Test failures: Review test output, fix code
- DMG errors: Check disk space, unmount existing DMGs
- Signing errors: Verify certificate installation
- Notarization errors: Check Apple Developer status

---

## Quick Reference Card

```
RELEASE CHECKLIST
─────────────────
1. Clean      → Option 28
2. Build      → Option 2
3. Test       → Option 8
4. DMG        → Option 23
5. Sign       → Option 24 (optional)
6. Notarize   → Option 25 (optional)

OR: One-command → Option 27
```

---

**Last Updated:** February 2026
**Marcedit Version:** 0.6.91+
**Build System:** build_tui.py v2.0
