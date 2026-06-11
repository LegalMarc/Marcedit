#!/usr/bin/env python3
"""
Verification script to check that the GUI test framework is properly installed.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print("🔍 Verifying GUI Test Framework Installation")
print("=" * 70)

errors = []
warnings = []
success = []

# Check Python version
print("\n1. Checking Python version...")
if sys.version_info >= (3, 8):
    success.append(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
else:
    errors.append(f"❌ Python 3.8+ required, found {sys.version_info.major}.{sys.version_info.minor}")

# Check core modules
print("\n2. Checking core modules...")
try:
    from tests.gui_harness import observer
    success.append("✅ observer.py loaded")
except Exception as e:
    errors.append(f"❌ observer.py failed: {e}")

try:
    from tests.gui_harness import interactions
    success.append("✅ interactions.py loaded")
except Exception as e:
    errors.append(f"❌ interactions.py failed: {e}")

try:
    from tests.gui_harness import live_editing_test
    success.append("✅ live_editing_test.py loaded")
except Exception as e:
    errors.append(f"❌ live_editing_test.py failed: {e}")

try:
    from tests.gui_harness import visual_editing_workflow
    success.append("✅ visual_editing_workflow.py loaded")
except Exception as e:
    errors.append(f"❌ visual_editing_workflow.py failed: {e}")

try:
    from tests.gui_harness import comprehensive_gui_test
    success.append("✅ comprehensive_gui_test.py loaded")
except Exception as e:
    errors.append(f"❌ comprehensive_gui_test.py failed: {e}")

# Check optional dependencies
print("\n3. Checking optional dependencies...")
try:
    from PIL import Image
    success.append("✅ PIL (Pillow) available - enhanced PDF verification")
except ImportError:
    warnings.append("⚠️  PIL (Pillow) not found - install with: pip3 install Pillow")

try:
    import pytesseract
    success.append("✅ pytesseract available - OCR-based verification")
except ImportError:
    warnings.append("⚠️  pytesseract not found - install with: pip3 install pytesseract")

# Check sample PDFs
print("\n4. Checking for sample PDFs...")
sample_dir = Path('ignored-resources/sample-files-marcedit')
if sample_dir.exists():
    pdfs = list(sample_dir.glob('*.pdf'))
    if pdfs:
        success.append(f"✅ Found {len(pdfs)} sample PDFs")
    else:
        warnings.append("⚠️  No sample PDFs found")
else:
    warnings.append("⚠️  Sample PDF directory not found")

# Check test runner script
print("\n5. Checking test runner script...")
runner_script = Path('tests/gui_harness/run_comprehensive_test.sh')
if runner_script.exists():
    if runner_script.stat().st_mode & 0o111:
        success.append("✅ Test runner script is executable")
    else:
        warnings.append("⚠️  Test runner script exists but not executable")
else:
    errors.append("❌ Test runner script not found")

# Print results
print("\n" + "=" * 70)
print("VERIFICATION RESULTS")
print("=" * 70)

if success:
    print(f"\n✅ Success ({len(success)}):")
    for item in success:
        print(f"  {item}")

if warnings:
    print(f"\n⚠️  Warnings ({len(warnings)}):")
    for item in warnings:
        print(f"  {item}")

if errors:
    print(f"\n❌ Errors ({len(errors)}):")
    for item in errors:
        print(f"  {item}")

# Final verdict
print("\n" + "=" * 70)
if not errors:
    if not warnings:
        print("🎉 INSTALLATION COMPLETE - All checks passed!")
    else:
        print("✅ INSTALLATION COMPLETE - Core functionality available")
        print("   (Install optional dependencies for enhanced features)")
    print("\n📖 Next steps:")
    print("   1. Open Marcedit")
    print("   2. Run: ./tests/gui_harness/run_comprehensive_test.sh")
    print("   3. Check the HTML report for results")
    sys.exit(0)
else:
    print("❌ INSTALLATION INCOMPLETE - Fix errors above")
    sys.exit(1)
