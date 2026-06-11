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

Use the same archive command without `CODE_SIGNING_ALLOWED=NO` once the signing identity, hardened runtime, entitlements, Developer ID certificate, and notary credentials are configured on the release runner.

Notarization and stapling should be verified on a clean machine before public-beta distribution.
