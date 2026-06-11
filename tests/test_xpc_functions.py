#!/usr/bin/env python3
"""
Test XPC-compatible functions
Week 5 Day 1: Font Detection Validation
"""

import sys
import os

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site')
sys.path.insert(0, python_site)

from editor_pkg import core_xpc

def test_identify_font():
    """Test font identification with a sample PDF"""
    print("\n=== Testing identify_font() ===")

    # Create a simple test PDF
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Hello World", fontsize=12, fontname="helv")
    test_pdf = "/tmp/test_xpc_font.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test font identification
    result = core_xpc.identify_font(test_pdf, 0, "Hello")

    print(f"Result: {result}")
    print(f"  Family: {result['family']}")
    print(f"  PostScript Name: {result['postscript_name']}")
    print(f"  Weight: {result['weight']}")
    print(f"  Width: {result['width']}")
    print(f"  Slant: {result['slant']}")
    print(f"  Size: {result['size']}")
    print(f"  X-Height: {result['x_height']}")
    print(f"  Cap-Height: {result['cap_height']}")

    # Verify basic structure
    assert 'family' in result, "Missing 'family' key"
    assert 'weight' in result, "Missing 'weight' key"
    assert 'size' in result, "Missing 'size' key"

    print("✅ identify_font() test passed!")

    # Cleanup
    os.remove(test_pdf)


def test_replace_text():
    """Test text replacement"""
    print("\n=== Testing replace_text() ===")

    # Create a simple test PDF
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Original Text", fontsize=12, fontname="helv")
    test_pdf = "/tmp/test_xpc_replace.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test text replacement
    result = core_xpc.replace_text(
        document_path=test_pdf,
        target_text="Original",
        replacement_text="Modified",
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 200, 'height': 200}
    )

    print(f"Result: {result}")
    print(f"  Success: {result['success']}")
    print(f"  Modified Path: {result['modified_path']}")
    print(f"  Warnings: {result['warnings']}")

    # Verify basic structure
    assert 'success' in result, "Missing 'success' key"
    assert 'warnings' in result, "Missing 'warnings' key"

    print("✅ replace_text() test passed!")

    # Cleanup
    os.remove(test_pdf)
    if result['modified_path'] and os.path.exists(result['modified_path']):
        os.remove(result['modified_path'])


def test_memento():
    """Test memento creation and restoration"""
    print("\n=== Testing create_memento() and restore_from_memento() ===")

    # Create a simple test PDF
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Memento Test", fontsize=12, fontname="helv")
    test_pdf = "/tmp/test_xpc_memento.pdf"
    doc.save(test_pdf)
    doc.close()

    # Create memento
    memento = core_xpc.create_memento(
        document_path=test_pdf,
        page_index=0,
        rect={'x': 0, 'y': 0, 'width': 200, 'height': 200}
    )

    print(f"Memento created: {memento}")
    print(f"  Page Index: {memento['page_index']}")
    print(f"  Content Stream Length: {len(memento['content_stream'])} bytes")

    assert 'page_index' in memento, "Missing 'page_index' key"
    assert 'content_stream' in memento, "Missing 'content_stream' key"

    # Restore from memento
    restore_result = core_xpc.restore_from_memento(
        document_path=test_pdf,
        memento=memento
    )

    print(f"Restore result: {restore_result}")
    assert restore_result['success'], "Restoration should succeed"
    assert os.path.exists(restore_result['output_path']), "Restored PDF does not exist"

    print("✅ memento operations test passed!")

    # Cleanup
    os.remove(test_pdf)
    if os.path.exists(restore_result['output_path']) and restore_result['output_path'] != test_pdf:
        os.remove(restore_result['output_path'])


def test_get_page_count():
    """Test page count function"""
    print("\n=== Testing get_page_count() ===")

    # Create a multi-page test PDF
    import fitz
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((100, 100), f"Page {i+1}", fontsize=12)
    test_pdf = "/tmp/test_xpc_pages.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test page count
    count = core_xpc.get_page_count(test_pdf)

    print(f"Page count: {count}")
    assert count == 5, f"Expected 5 pages, got {count}"

    print("✅ get_page_count() test passed!")

    # Cleanup
    os.remove(test_pdf)


if __name__ == '__main__':
    print("Testing XPC-Compatible Functions")
    print("=" * 50)

    try:
        test_get_page_count()
        test_identify_font()
        test_replace_text()
        test_memento()

        print("\n" + "=" * 50)
        print("✅ All XPC function tests passed!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
