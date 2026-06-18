# Marcedit Release Checklist

## Local validation

Run the curated public-beta checks before archiving:

```bash
python3 -m pip install -r requirements-lock.txt
python3 -m pytest tests/test_editor_core.py tests/test_reflow_synthesizer.py tests/test_performance_regression.py tests/test_week6_collision.py tests/test_week6_unicode.py tests/test_security.py -v
tests/run_visual_tests.sh python
xcodebuild build -scheme MarceditUITests -destination 'platform=macOS'
```

Visual/GUI harnesses that capture document-derived screenshots or send evaluator input to an external API require explicit opt-in environment variables.

## Archive dry run

```bash
xcodebuild archive \
  -scheme MarceditUITests \
  -destination 'generic/platform=macOS' \
  -archivePath "$PWD/build/Marcedit.xcarchive" \
  CODE_SIGNING_ALLOWED=NO
test -d "$PWD/build/Marcedit.xcarchive/Products/Applications/Marcedit.app"
```

## Signed release path

**`Scripts/sign_notarize_release.sh` is the only supported way to produce a distributable build.**

The script handles Developer ID signing, `notarytool` submission, stapling, `spctl` gatekeeper verification, and `verify_release_security.py`. Run it instead of invoking `xcodebuild` directly for any release you intend to distribute:

```bash
Scripts/sign_notarize_release.sh
```

> **Warning:** a plain `xcodebuild -configuration Release` (or the archive dry run above without the script) yields an **ad-hoc-signed, non-notarizable** app because `project.pbxproj` sets `CODE_SIGN_IDENTITY="-"` and the embedded build phase uses `--timestamp=none`. **Do not distribute a build produced this way.**

Notarization and stapling must be verified on a clean machine before public-beta distribution.
