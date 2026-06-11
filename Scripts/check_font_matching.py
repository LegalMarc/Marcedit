#!/usr/bin/env python3
"""
Test if font matching works with the current test PDF
"""

import sys
import time
sys.path.insert(0, "Sources/Marcedit/python_site")

try:
    from editor_pkg.core import identify_font

    test_pdf = "test_text_selection.pdf"
    target_text = "TARGET TEXT LINE 1"

    print("Testing font identification...")
    print(f"PDF: {test_pdf}")
    print(f"Text: {target_text}")
    print()

    start = time.time()

    try:
        result = identify_font(
            input_path=test_pdf,
            page_number=1,
            target_text=target_text
        )

        elapsed = time.time() - start

        print(f"✓ Font identification completed in {elapsed:.2f} seconds")
        print(f"Result: {result}")
        sys.exit(0)

    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ Font identification failed after {elapsed:.2f} seconds")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

except ImportError as e:
    print(f"✗ Failed to import: {e}")
    sys.exit(1)
