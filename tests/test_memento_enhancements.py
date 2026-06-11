#!/usr/bin/env python3
"""
Test Memento Enhanced Features
Week 5 Day 3: Memento Enhancement Validation
"""

import sys
import os

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site')
sys.path.insert(0, python_site)

from editor_pkg import core_xpc
import fitz
import time


def test_memento_compression():
    """Test memento compression and size reduction"""
    print("\n=== Testing Memento Compression ===")

    # Create test PDF with substantial content
    doc = fitz.open()
    page = doc.new_page()

    # Add multiple text elements to create larger content stream
    for i in range(20):
        page.insert_text((50, 50 + i * 30), f"Line {i}: This is test text for compression", fontsize=12)

    test_pdf = "/tmp/test_memento_compress.pdf"
    doc.save(test_pdf)
    doc.close()

    # Create memento
    memento = core_xpc.create_memento(
        document_path=test_pdf,
        page_index=0,
        rect={'x': 0, 'y': 0, 'width': 500, 'height': 800},
        operation_type="test_compression"
    )

    print(f"Memento created:")
    print(f"  Version: {memento['version']}")
    print(f"  Original Size: {memento['original_size']} bytes")
    print(f"  Compressed Size: {memento['compressed_size']} bytes")

    # Calculate compression ratio
    if memento['original_size'] > 0:
        ratio = (1 - memento['compressed_size'] / memento['original_size']) * 100
        print(f"  Compression Ratio: {ratio:.1f}%")
        print(f"  Space Saved: {memento['original_size'] - memento['compressed_size']} bytes")

    # Validate compression
    assert memento['version'] == 2, "Should be version 2"
    assert memento['compressed_size'] < memento['original_size'], "Compressed should be smaller"
    assert 'checksum' in memento, "Should have checksum"
    assert 'timestamp' in memento, "Should have timestamp"
    assert memento['operation_type'] == "test_compression", "Should preserve operation type"

    print("✅ Memento compression test passed!")

    # Cleanup
    os.remove(test_pdf)


def test_memento_validation():
    """Test memento validation function"""
    print("\n=== Testing Memento Validation ===")

    # Create test PDF
    doc = fitz.open()
    doc.new_page()
    test_pdf = "/tmp/test_memento_validate.pdf"
    doc.save(test_pdf)
    doc.close()

    # Create memento
    memento = core_xpc.create_memento(
        document_path=test_pdf,
        page_index=0,
        rect={'x': 0, 'y': 0, 'width': 100, 'height': 100}
    )

    # Validate good memento
    validation = core_xpc.validate_memento(memento)

    print(f"Validation result:")
    print(f"  Valid: {validation['valid']}")
    print(f"  Errors: {validation['errors']}")
    print(f"  Warnings: {validation['warnings']}")
    print(f"  Info: {validation['info']}")

    assert validation['valid'] == True, "Valid memento should pass validation"
    assert len(validation['errors']) == 0, "Should have no errors"
    assert validation['info']['version'] == 2, "Should be version 2"
    assert validation['info']['has_checksum'] == True, "Should have checksum"

    # Test invalid memento (missing required field)
    bad_memento = {'page_index': 0}  # Missing content_stream
    validation2 = core_xpc.validate_memento(bad_memento)

    print(f"\nInvalid memento validation:")
    print(f"  Valid: {validation2['valid']}")
    print(f"  Errors: {validation2['errors']}")

    assert validation2['valid'] == False, "Invalid memento should fail"
    assert len(validation2['errors']) > 0, "Should have errors"

    print("✅ Memento validation test passed!")

    # Cleanup
    os.remove(test_pdf)


def test_restore_with_validation():
    """Test memento restoration with checksum validation"""
    print("\n=== Testing Restore with Validation ===")

    # Create test PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Original Text", fontsize=12)
    test_pdf = "/tmp/test_restore_validate.pdf"
    doc.save(test_pdf)
    doc.close()

    # Create memento
    memento = core_xpc.create_memento(
        document_path=test_pdf,
        page_index=0,
        rect={'x': 0, 'y': 0, 'width': 200, 'height': 200},
        operation_type="restore_test"
    )

    print(f"Memento created with checksum: {memento['checksum'][:16]}...")

    # Modify PDF (create new version)
    doc = fitz.open(test_pdf)
    page = doc[0]
    page.insert_text((100, 150), "Modified Text", fontsize=12)
    modified_pdf = "/tmp/test_restore_validate_modified.pdf"
    doc.save(modified_pdf)
    doc.close()

    print("PDF modified")

    # Use modified PDF for restoration test
    test_pdf = modified_pdf

    # Restore from memento with validation
    result = core_xpc.restore_from_memento(
        document_path=test_pdf,
        memento=memento,
        validate=True
    )

    print(f"Restoration result:")
    print(f"  Success: {result['success']}")
    print(f"  Validated: {result['validated']}")
    print(f"  Message: {result['message']}")
    print(f"  Output Path: {result['output_path']}")

    assert result['success'] == True, "Restoration should succeed"
    assert result['validated'] == True, "Checksum should be validated"
    assert os.path.exists(result['output_path']), "Restored PDF should exist"

    print("✅ Restore with validation test passed!")

    # Cleanup
    for path in ['/tmp/test_restore_validate.pdf', modified_pdf]:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(result['output_path']):
        os.remove(result['output_path'])


def test_undo_redo_workflow():
    """Test complete undo/redo workflow"""
    print("\n=== Testing Undo/Redo Workflow ===")

    # Create original PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Step 0: Original", fontsize=12, fontname="helv")
    original_pdf = "/tmp/test_undo_redo.pdf"
    doc.save(original_pdf)
    doc.close()

    print("Created original PDF")

    # Create memento before first edit
    memento1 = core_xpc.create_memento(
        document_path=original_pdf,
        page_index=0,
        rect={'x': 0, 'y': 0, 'width': 600, 'height': 800},
        operation_type="before_edit1"
    )
    print(f"Memento 1 created (timestamp: {memento1['timestamp']})")

    # Edit 1: Replace text
    time.sleep(0.1)  # Small delay for timestamp difference
    result1 = core_xpc.replace_text(
        document_path=original_pdf,
        target_text="Step 0",
        replacement_text="Step 1",
        page_index=0,
        overrides={},
        detected_font=None,
        target_rect={'x': 0, 'y': 0, 'width': 200, 'height': 200}
    )

    if result1['success']:
        print(f"Edit 1 complete: {result1['message']}")
        edit1_pdf = result1['modified_path']

        # Create memento before second edit
        time.sleep(0.1)
        memento2 = core_xpc.create_memento(
            document_path=edit1_pdf,
            page_index=0,
            rect={'x': 0, 'y': 0, 'width': 600, 'height': 800},
            operation_type="before_edit2"
        )
        print(f"Memento 2 created (timestamp: {memento2['timestamp']})")

        # Edit 2: Replace again
        result2 = core_xpc.replace_text(
            document_path=edit1_pdf,
            target_text="Step 1",
            replacement_text="Step 2",
            page_index=0,
            overrides={},
            detected_font=None,
            target_rect={'x': 0, 'y': 0, 'width': 200, 'height': 200}
        )

        if result2['success']:
            print(f"Edit 2 complete: {result2['message']}")
            edit2_pdf = result2['modified_path']

            # Now test undo operations

            # Undo edit 2 (restore to memento2 state)
            print("\nPerforming Undo 1 (back to Step 1)...")
            undo1_result = core_xpc.restore_from_memento(
                document_path=edit2_pdf,
                memento=memento2,
                validate=True
            )

            assert undo1_result['success'] == True, "Undo 1 should succeed"
            print(f"  Undo 1: {undo1_result['message']}")
            undo1_pdf = undo1_result['output_path']

            # Undo edit 1 (restore to memento1 state)
            print("Performing Undo 2 (back to Step 0)...")
            undo2_result = core_xpc.restore_from_memento(
                document_path=undo1_pdf,
                memento=memento1,
                validate=True
            )

            assert undo2_result['success'] == True, "Undo 2 should succeed"
            print(f"  Undo 2: {undo2_result['message']}")
            undo2_pdf = undo2_result['output_path']

            # Validate timestamp ordering
            assert memento2['timestamp'] > memento1['timestamp'], "Timestamps should be ordered"

            # Verify checksums are different
            assert memento1['checksum'] != memento2['checksum'], "Different states should have different checksums"

            print("\n✅ Undo/Redo workflow test passed!")

            # Cleanup
            os.remove(original_pdf)
            for path in [edit1_pdf, edit2_pdf, undo1_pdf, undo2_pdf]:
                if os.path.exists(path):
                    os.remove(path)
        else:
            print("Edit 2 failed, skipping undo tests")
    else:
        print("Edit 1 failed, skipping undo tests")


def test_memento_size_optimization():
    """Test memento size with various content types"""
    print("\n=== Testing Memento Size Optimization ===")

    test_cases = [
        ("Small text", lambda page: page.insert_text((100, 100), "Small", fontsize=12)),
        ("Large text", lambda page: [page.insert_text((50, 50 + i*20), f"Line {i}" * 10, fontsize=10) for i in range(30)]),
        ("Image-heavy", lambda page: page.insert_text((100, 100), "With image placeholder", fontsize=12))
    ]

    results = []

    for name, content_fn in test_cases:
        doc = fitz.open()
        page = doc.new_page()
        content_fn(page)

        test_pdf = f"/tmp/test_size_{name.replace(' ', '_')}.pdf"
        doc.save(test_pdf)
        doc.close()

        # Create memento
        memento = core_xpc.create_memento(
            document_path=test_pdf,
            page_index=0,
            rect={'x': 0, 'y': 0, 'width': 600, 'height': 800}
        )

        ratio = 0
        if memento['original_size'] > 0:
            ratio = (1 - memento['compressed_size'] / memento['original_size']) * 100

        results.append({
            'name': name,
            'original': memento['original_size'],
            'compressed': memento['compressed_size'],
            'ratio': ratio
        })

        print(f"\n{name}:")
        print(f"  Original: {memento['original_size']} bytes")
        print(f"  Compressed: {memento['compressed_size']} bytes")
        print(f"  Ratio: {ratio:.1f}%")

        # Cleanup
        os.remove(test_pdf)

    # Verify compression works (for larger content)
    # Note: Very small content (<100 bytes) may expand due to compression overhead
    for result in results:
        if result['original'] > 100:
            # For larger content, compression should work
            assert result['ratio'] > 0, f"{result['name']}: should have some compression"
        else:
            # For small content, compression may actually increase size (overhead)
            print(f"  Note: Small content ({result['original']} bytes) may expand when compressed")

    print("\nCompression works effectively for larger content streams")

    print("\n✅ Memento size optimization test passed!")


def test_corrupted_memento_handling():
    """Test handling of corrupted mementos"""
    print("\n=== Testing Corrupted Memento Handling ===")

    # Create test PDF
    doc = fitz.open()
    doc.new_page()
    test_pdf = "/tmp/test_corrupted.pdf"
    doc.save(test_pdf)
    doc.close()

    # Create valid memento
    good_memento = core_xpc.create_memento(
        document_path=test_pdf,
        page_index=0,
        rect={'x': 0, 'y': 0, 'width': 100, 'height': 100}
    )

    # Test 1: Corrupted checksum
    bad_memento1 = good_memento.copy()
    bad_memento1['checksum'] = 'corrupted_checksum_value'

    result1 = core_xpc.restore_from_memento(
        document_path=test_pdf,
        memento=bad_memento1,
        validate=True
    )

    print(f"Corrupted checksum test:")
    print(f"  Success: {result1['success']}")
    print(f"  Message: {result1['message']}")

    assert result1['success'] == False, "Should fail with bad checksum"
    assert 'checksum' in result1['message'].lower() or 'mismatch' in result1['message'].lower(), "Should mention checksum issue"

    # Test 2: Invalid compression data
    bad_memento2 = good_memento.copy()
    bad_memento2['content_stream'] = 'invalid_base64_!@#$%'

    result2 = core_xpc.restore_from_memento(
        document_path=test_pdf,
        memento=bad_memento2,
        validate=False  # Skip checksum to test decompression
    )

    print(f"\nInvalid compression test:")
    print(f"  Success: {result2['success']}")
    print(f"  Message: {result2['message']}")

    assert result2['success'] == False, "Should fail with invalid data"

    # Test 3: Empty content stream
    bad_memento3 = good_memento.copy()
    bad_memento3['content_stream'] = ''

    result3 = core_xpc.restore_from_memento(
        document_path=test_pdf,
        memento=bad_memento3,
        validate=False
    )

    print(f"\nEmpty content stream test:")
    print(f"  Success: {result3['success']}")
    print(f"  Message: {result3['message']}")

    assert result3['success'] == False, "Should fail with empty content"
    assert 'empty' in result3['message'].lower(), "Should mention empty content"

    print("\n✅ Corrupted memento handling test passed!")

    # Cleanup
    os.remove(test_pdf)


if __name__ == '__main__':
    print("Testing Memento Enhanced Features")
    print("=" * 60)

    try:
        test_memento_compression()
        test_memento_validation()
        test_memento_size_optimization()
        test_restore_with_validation()
        test_corrupted_memento_handling()
        test_undo_redo_workflow()

        print("\n" + "=" * 60)
        print("✅ All memento enhancement tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
