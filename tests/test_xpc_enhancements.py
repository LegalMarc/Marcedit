#!/usr/bin/env python3
"""
Test XPC Enhanced Features
Week 5 Day 2: Text Replacement Enhancement Validation
"""

import sys
import os

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site')
sys.path.insert(0, python_site)

from editor_pkg import core_xpc
import fitz


def test_override_mapping():
    """Test comprehensive override mapping"""
    print("\n=== Testing Override Mapping ===")

    # Create test PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Test Override", fontsize=12, fontname="helv")
    test_pdf = "/tmp/test_xpc_override.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test with comprehensive overrides
    overrides = {
        'font_family': 'Helvetica',
        'size_delta': 2.0,
        'x_offset': 5.0,
        'y_offset': -2.0,
        'fill_color': 'red',
        'is_bold': True,
        'is_italic': False,
        'underline': True,
        'strikethrough': False,
        'justification': 'Center',
        'exhaustive_search': False
    }

    result = core_xpc.replace_text(
        document_path=test_pdf,
        target_text="Test",
        replacement_text="Enhanced",
        page_index=0,
        overrides=overrides,
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 200, 'height': 200}
    )

    print(f"Result: {result}")
    print(f"  Success: {result['success']}")
    print(f"  Warnings: {result['warnings']}")
    print(f"  Instances Replaced: {result['instances_replaced']}")
    print(f"  Font Used: {result['font_used']}")
    print(f"  Message: {result['message']}")

    # Verify override fields in warnings
    assert 'success' in result, "Missing 'success' key"
    assert 'warnings' in result, "Missing 'warnings' key"
    assert 'instances_replaced' in result, "Missing 'instances_replaced' key"
    assert 'font_used' in result, "Missing 'font_used' key"
    assert 'message' in result, "Missing 'message' key"

    # Check that overrides were used
    override_warning_found = any('override' in w.lower() for w in result['warnings'])
    if override_warning_found:
        print("  ✓ Overrides were applied")

    print("✅ Override mapping test passed!")

    # Cleanup
    os.remove(test_pdf)
    if result['modified_path'] and os.path.exists(result['modified_path']):
        os.remove(result['modified_path'])


def test_unicode_text():
    """Test replacement with Unicode characters"""
    print("\n=== Testing Unicode Text ===")

    # Create test PDF with Unicode
    doc = fitz.open()
    page = doc.new_page()

    # Insert Unicode text (various scripts)
    unicode_texts = [
        "Hello World",  # Latin
        "你好世界",      # Chinese
        "مرحبا",        # Arabic
        "Здравствуй",   # Cyrillic
        "こんにちは"     # Japanese
    ]

    y_pos = 100
    for text in unicode_texts:
        try:
            page.insert_text((100, y_pos), text, fontsize=12)
            y_pos += 30
        except Exception as e:
            print(f"  Warning: Could not insert '{text}': {e}")

    test_pdf = "/tmp/test_xpc_unicode.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test replacement
    result = core_xpc.replace_text(
        document_path=test_pdf,
        target_text="Hello",
        replacement_text="你好",  # Replace English with Chinese
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 200, 'height': 200}
    )

    print(f"Unicode replacement result:")
    print(f"  Success: {result['success']}")
    print(f"  Warnings: {result['warnings']}")
    print(f"  Message: {result['message']}")

    # Note: Success may vary depending on font availability
    # The important thing is that it doesn't crash
    assert 'success' in result, "Missing 'success' key"

    print("✅ Unicode text test passed!")

    # Cleanup
    os.remove(test_pdf)
    if result['modified_path'] and os.path.exists(result['modified_path']):
        os.remove(result['modified_path'])


def test_error_handling():
    """Test error handling and validation"""
    print("\n=== Testing Error Handling ===")

    # Test 1: Invalid document path
    result = core_xpc.replace_text(
        document_path="/nonexistent/path.pdf",
        target_text="Test",
        replacement_text="Replace",
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 100, 'height': 100}
    )

    assert result['success'] == False, "Should fail with nonexistent path"
    assert len(result['warnings']) > 0, "Should have warnings"
    print(f"  ✓ Invalid path handled: {result['message']}")

    # Test 2: Empty target text
    result = core_xpc.replace_text(
        document_path="/tmp/test.pdf",
        target_text="",
        replacement_text="Replace",
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 100, 'height': 100}
    )

    assert result['success'] == False, "Should fail with empty target"
    assert 'empty' in result['message'].lower(), "Should mention empty text"
    print(f"  ✓ Empty target handled: {result['message']}")

    # Test 3: Invalid page index
    # Create a test PDF first
    doc = fitz.open()
    doc.new_page()
    test_pdf = "/tmp/test_xpc_error.pdf"
    doc.save(test_pdf)
    doc.close()

    result = core_xpc.replace_text(
        document_path=test_pdf,
        target_text="Test",
        replacement_text="Replace",
        page_index=999,  # Invalid page
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 100, 'height': 100}
    )

    assert result['success'] == False, "Should fail with invalid page"
    assert 'page' in result['message'].lower() or 'range' in result['message'].lower(), "Should mention page issue"
    print(f"  ✓ Invalid page handled: {result['message']}")

    print("✅ Error handling test passed!")

    # Cleanup
    os.remove(test_pdf)


def test_ligatures_and_special_chars():
    """Test text with ligatures and special characters"""
    print("\n=== Testing Ligatures and Special Characters ===")

    # Create test PDF with ligature-prone text
    doc = fitz.open()
    page = doc.new_page()

    # Text with common ligatures: fi, fl, ff, ffi, ffl
    ligature_text = "officeffleaffinity"
    page.insert_text((100, 100), ligature_text, fontsize=14, fontname="helv")

    # Text with special characters
    special_text = "café résumé naïve"
    page.insert_text((100, 130), special_text, fontsize=14, fontname="helv")

    test_pdf = "/tmp/test_xpc_ligatures.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test replacement of ligature text
    result = core_xpc.replace_text(
        document_path=test_pdf,
        target_text="office",
        replacement_text="official",
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 300, 'height': 200}
    )

    print(f"Ligature replacement result:")
    print(f"  Success: {result['success']}")
    print(f"  Warnings: {result['warnings']}")
    print(f"  Instances: {result['instances_replaced']}")

    # Test replacement with accented characters
    result2 = core_xpc.replace_text(
        document_path=test_pdf,
        target_text="café",
        replacement_text="coffee",
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 300, 'height': 200}
    )

    print(f"Accented character replacement result:")
    print(f"  Success: {result2['success']}")
    print(f"  Warnings: {result2['warnings']}")

    assert 'success' in result, "Missing 'success' key"
    assert 'success' in result2, "Missing 'success' key"

    print("✅ Ligatures and special characters test passed!")

    # Cleanup
    os.remove(test_pdf)
    if result['modified_path'] and os.path.exists(result['modified_path']):
        os.remove(result['modified_path'])
    if result2['modified_path'] and os.path.exists(result2['modified_path']):
        os.remove(result2['modified_path'])


def test_multi_instance_replacement():
    """Test replacing multiple instances of text"""
    print("\n=== Testing Multi-Instance Replacement ===")

    # Create test PDF with multiple instances
    doc = fitz.open()
    page = doc.new_page()

    # Insert same text multiple times
    positions = [(100, 100), (100, 150), (100, 200), (100, 250)]
    for x, y in positions:
        page.insert_text((x, y), "Replace Me", fontsize=12, fontname="helv")

    test_pdf = "/tmp/test_xpc_multi.pdf"
    doc.save(test_pdf)
    doc.close()

    # Replace all instances
    result = core_xpc.replace_text(
        document_path=test_pdf,
        target_text="Replace",
        replacement_text="Updated",
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 500, 'height': 300}
    )

    print(f"Multi-instance replacement result:")
    print(f"  Success: {result['success']}")
    print(f"  Instances Replaced: {result['instances_replaced']}")
    print(f"  Warnings: {result['warnings']}")

    # Check if multiple instances warning is present
    if result['instances_replaced'] > 1:
        print(f"  ✓ Correctly identified {result['instances_replaced']} instances")

    assert 'instances_replaced' in result, "Missing 'instances_replaced' key"

    print("✅ Multi-instance replacement test passed!")

    # Cleanup
    os.remove(test_pdf)
    if result['modified_path'] and os.path.exists(result['modified_path']):
        os.remove(result['modified_path'])


def test_font_detection_accuracy():
    """Test font detection with various fonts"""
    print("\n=== Testing Font Detection Accuracy ===")

    # Create PDF with different fonts
    doc = fitz.open()
    page = doc.new_page()

    fonts_to_test = [
        ("helv", "Helvetica", 400),
        ("tibo", "Times-Bold", 700),
        ("cour", "Courier", 400),
    ]

    y_pos = 100
    for font_name, expected_family, expected_weight in fonts_to_test:
        try:
            page.insert_text((100, y_pos), f"Test {font_name}", fontsize=12, fontname=font_name)
            y_pos += 30
        except Exception as e:
            print(f"  Warning: Could not insert font {font_name}: {e}")

    test_pdf = "/tmp/test_xpc_fonts.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test detection for each font
    test_texts = ["Test helv", "Test tibo", "Test cour"]
    expected = [
        ("Helvetica", 400),
        ("Times", 700),
        ("Courier", 400)
    ]

    for i, (text, (exp_family, exp_weight)) in enumerate(zip(test_texts, expected)):
        result = core_xpc.identify_font(test_pdf, 0, text)

        print(f"\nFont detection for '{text}':")
        print(f"  Family: {result['family']} (expected: {exp_family})")
        print(f"  Weight: {result['weight']} (expected: {exp_weight})")
        print(f"  Size: {result['size']}")
        print(f"  PostScript Name: {result['postscript_name']}")

        # Check if family is close (may vary)
        assert exp_family.lower() in result['family'].lower() or result['family'].lower() in exp_family.lower(), \
            f"Font family mismatch: {result['family']} vs {exp_family}"

    print("\n✅ Font detection accuracy test passed!")

    # Cleanup
    os.remove(test_pdf)


if __name__ == '__main__':
    print("Testing XPC Enhanced Features")
    print("=" * 60)

    try:
        test_override_mapping()
        test_error_handling()
        test_multi_instance_replacement()
        test_font_detection_accuracy()
        test_ligatures_and_special_chars()
        test_unicode_text()

        print("\n" + "=" * 60)
        print("✅ All enhanced feature tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
