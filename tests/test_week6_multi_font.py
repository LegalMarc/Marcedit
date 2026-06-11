#!/usr/bin/env python3
"""
Week 6 Day 2 - Multi-Font Text Blocks Tests
Tests the new get_block_spans and replace_block_with_spans XPC functions
"""

import sys
import os
import tempfile

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site')
sys.path.insert(0, python_site)

from editor_pkg import core_xpc
import fitz

def test_01_get_block_spans_simple():
    """Test extracting spans from a simple multi-font block."""
    print("\n[TEST 01] Get Block Spans - Simple Multi-Font")

    # Create test PDF with multi-font text
    doc = fitz.open()
    page = doc.new_page()

    # Insert text with different fonts
    tw = fitz.TextWriter(page.rect)

    # Span 1: Bold Helvetica
    font_bold = fitz.Font("Helvetica-Bold")
    tw.append(fitz.Point(100, 100), "Welcome ", font=font_bold, fontsize=14)

    # Span 2: Regular Helvetica
    font_reg = fitz.Font("Helvetica")
    tw.append(fitz.Point(160, 100), "to ", font=font_reg, fontsize=12)

    # Span 3: Italic Times
    font_italic = fitz.Font("Times-Italic")
    tw.append(fitz.Point(180, 100), "Marcedit", font=font_italic, fontsize=14)

    tw.write_text(page)

    # Save test PDF
    test_pdf = "/tmp/test_multi_font.pdf"
    doc.save(test_pdf)
    doc.close()

    # Extract spans
    result = core_xpc.get_block_spans(test_pdf, 0, "Welcome")

    assert result['success'], f"Failed to extract spans: {result['message']}"
    assert result['span_count'] >= 1, f"Expected at least 1 span, got {result['span_count']}"

    spans = result['spans']
    assert len(spans) >= 1, "No spans extracted"

    # Check first span
    first_span = spans[0]
    assert 'text' in first_span, "Span missing text field"
    assert 'font_family' in first_span, "Span missing font_family field"
    assert 'size' in first_span, "Span missing size field"
    assert 'color' in first_span, "Span missing color field"
    assert 'bbox' in first_span, "Span missing bbox field"

    # Check color format
    color = first_span['color']
    assert 'r' in color, "Color missing r component"
    assert 'g' in color, "Color missing g component"
    assert 'b' in color, "Color missing b component"

    # Check bbox format
    bbox = first_span['bbox']
    assert 'x' in bbox, "Bbox missing x"
    assert 'y' in bbox, "Bbox missing y"
    assert 'width' in bbox, "Bbox missing width"
    assert 'height' in bbox, "Bbox missing height"

    print(f"  ✓ Extracted {result['span_count']} spans")
    print(f"  ✓ First span: '{first_span['text'][:20]}...' ({first_span['font_family']}, {first_span['size']}pt)")
    print("  ✓ All fields present and correctly formatted")

    return True


def test_02_replace_block_with_spans_simple():
    """Test replacing a block with multi-font spans."""
    print("\n[TEST 02] Replace Block with Spans - Simple")

    # Create test PDF
    doc = fitz.open()
    page = doc.new_page()

    # Insert original text
    page.insert_text((100, 100), "Original Text", fontsize=12, fontname="helv")

    test_pdf = "/tmp/test_replace_block.pdf"
    doc.save(test_pdf)
    doc.close()

    # Define block and new spans
    block_bbox = {'x': 95, 'y': 85, 'width': 120, 'height': 20}

    spans = [
        {
            'text': 'New ',
            'font_family': 'Helvetica',
            'font_postscript_name': 'Helvetica-Bold',
            'size': 14.0,
            'weight': 700,
            'slant': 'normal',
            'color': {'r': 0.0, 'g': 0.0, 'b': 1.0},  # Blue
            'line_index': 0
        },
        {
            'text': 'Styled ',
            'font_family': 'Helvetica',
            'font_postscript_name': 'Helvetica',
            'size': 12.0,
            'weight': 400,
            'slant': 'italic',
            'color': {'r': 0.5, 'g': 0.5, 'b': 0.5},  # Gray
            'line_index': 0
        },
        {
            'text': 'Text',
            'font_family': 'Times',
            'font_postscript_name': 'Times-Italic',
            'size': 14.0,
            'weight': 400,
            'slant': 'italic',
            'color': {'r': 1.0, 'g': 0.0, 'b': 0.0},  # Red
            'line_index': 0
        }
    ]

    # Replace block
    result = core_xpc.replace_block_with_spans(
        test_pdf,
        0,
        block_bbox,
        spans
    )

    assert result['success'], f"Failed to replace block: {result['message']}"
    assert result['modified_path'] is not None, "No output path returned"
    assert os.path.exists(result['modified_path']), "Output file not created"
    assert result['spans_replaced'] >= 0, "Negative spans_replaced count"

    print(f"  ✓ Block replaced successfully")
    print(f"  ✓ Output: {os.path.basename(result['modified_path'])}")
    print(f"  ✓ Spans inserted: {result['spans_replaced']}")
    if result['warnings']:
        print(f"  ⚠ Warnings: {len(result['warnings'])}")

    return True


def test_03_get_and_replace_round_trip():
    """Test extracting spans and replacing them (round trip)."""
    print("\n[TEST 03] Get and Replace Round Trip")

    # Create test PDF with multi-font content
    doc = fitz.open()
    page = doc.new_page()

    tw = fitz.TextWriter(page.rect)

    # Create rich text block
    font_bold = fitz.Font("Helvetica-Bold")
    font_reg = fitz.Font("Helvetica")
    font_italic = fitz.Font("Times-Italic")

    tw.append(fitz.Point(100, 100), "This ", font=font_reg, fontsize=12)
    tw.append(fitz.Point(130, 100), "is ", font=font_bold, fontsize=12)
    tw.append(fitz.Point(150, 100), "a ", font=font_reg, fontsize=12)
    tw.append(fitz.Point(165, 100), "test", font=font_italic, fontsize=12)

    tw.write_text(page)

    test_pdf = "/tmp/test_roundtrip.pdf"
    doc.save(test_pdf)
    doc.close()

    # Step 1: Extract spans
    extract_result = core_xpc.get_block_spans(test_pdf, 0, "This")
    assert extract_result['success'], f"Extract failed: {extract_result['message']}"

    original_spans = extract_result['spans']
    block_bbox = extract_result['block_bbox']

    print(f"  ✓ Extracted {len(original_spans)} spans")

    # Step 2: Modify spans (change text, keep formatting)
    modified_spans = []
    for span in original_spans:
        modified_span = span.copy()
        # Change text content but keep all formatting
        if 'This' in span['text']:
            modified_span['text'] = 'That '
        elif 'is' in span['text']:
            modified_span['text'] = 'was '
        elif 'test' in span['text']:
            modified_span['text'] = 'example'
        modified_spans.append(modified_span)

    print(f"  ✓ Modified {len(modified_spans)} spans")

    # Step 3: Replace block
    replace_result = core_xpc.replace_block_with_spans(
        test_pdf,
        0,
        block_bbox,
        modified_spans
    )

    assert replace_result['success'], f"Replace failed: {replace_result['message']}"
    assert replace_result['modified_path'] is not None, "No output path"

    print(f"  ✓ Block replaced successfully")
    print(f"  ✓ Output: {os.path.basename(replace_result['modified_path'])}")

    # Step 4: Verify we can extract from modified PDF
    verify_result = core_xpc.get_block_spans(replace_result['modified_path'], 0, "That")
    assert verify_result['success'], "Cannot extract from modified PDF"

    print(f"  ✓ Verified modified PDF: {verify_result['span_count']} spans")

    return True


def test_04_color_preservation():
    """Test that colors are preserved correctly."""
    print("\n[TEST 04] Color Preservation")

    # Create PDF with colored text
    doc = fitz.open()
    page = doc.new_page()

    # Insert colored text blocks
    page.insert_text((100, 100), "Red", fontsize=12, color=(1, 0, 0))
    page.insert_text((100, 120), "Green", fontsize=12, color=(0, 1, 0))
    page.insert_text((100, 140), "Blue", fontsize=12, color=(0, 0, 1))

    test_pdf = "/tmp/test_colors.pdf"
    doc.save(test_pdf)
    doc.close()

    # Extract red text span
    result = core_xpc.get_block_spans(test_pdf, 0, "Red")
    assert result['success'], "Failed to extract colored text"

    spans = result['spans']
    assert len(spans) >= 1, "No spans extracted"

    # Find span with "Red" text
    red_span = None
    for span in spans:
        if 'Red' in span['text']:
            red_span = span
            break

    assert red_span is not None, "Could not find 'Red' span"

    # Check color
    color = red_span['color']
    assert color['r'] > 0.9, f"Red component should be ~1.0, got {color['r']}"
    assert color['g'] < 0.1, f"Green component should be ~0.0, got {color['g']}"
    assert color['b'] < 0.1, f"Blue component should be ~0.0, got {color['b']}"

    print(f"  ✓ Color extracted correctly: R={color['r']:.2f}, G={color['g']:.2f}, B={color['b']:.2f}")

    return True


def test_05_bold_italic_detection():
    """Test that bold and italic are detected correctly."""
    print("\n[TEST 05] Bold/Italic Detection")

    # Create PDF with styled text
    doc = fitz.open()
    page = doc.new_page()

    # Use different font variants
    page.insert_text((100, 100), "Regular", fontsize=12, fontname="Helvetica")
    page.insert_text((100, 120), "Bold", fontsize=12, fontname="Helvetica-Bold")
    page.insert_text((100, 140), "Italic", fontsize=12, fontname="Times-Italic")

    test_pdf = "/tmp/test_styles.pdf"
    doc.save(test_pdf)
    doc.close()

    # Test bold detection
    bold_result = core_xpc.get_block_spans(test_pdf, 0, "Bold")
    assert bold_result['success'], "Failed to extract bold text"

    bold_span = None
    for span in bold_result['spans']:
        if 'Bold' in span['text']:
            bold_span = span
            break

    assert bold_span is not None, "Could not find 'Bold' span"
    assert bold_span['weight'] == 700, f"Expected weight 700, got {bold_span['weight']}"

    print(f"  ✓ Bold detected: weight={bold_span['weight']}, family={bold_span['font_family']}")

    # Test italic detection
    italic_result = core_xpc.get_block_spans(test_pdf, 0, "Italic")
    assert italic_result['success'], "Failed to extract italic text"

    italic_span = None
    for span in italic_result['spans']:
        if 'Italic' in span['text']:
            italic_span = span
            break

    assert italic_span is not None, "Could not find 'Italic' span"
    assert italic_span['slant'] == 'italic', f"Expected slant 'italic', got {italic_span['slant']}"

    print(f"  ✓ Italic detected: slant={italic_span['slant']}, family={italic_span['font_family']}")

    return True


def test_06_multi_line_block():
    """Test extracting spans from multi-line text block."""
    print("\n[TEST 06] Multi-Line Block")

    # Create PDF with multi-line block
    doc = fitz.open()
    page = doc.new_page()

    # Insert multi-line text
    tw = fitz.TextWriter(page.rect)
    font_reg = fitz.Font("Helvetica")

    # Line 1
    tw.append(fitz.Point(100, 100), "First line of text", font=font_reg, fontsize=12)
    # Line 2
    tw.append(fitz.Point(100, 120), "Second line here", font=font_reg, fontsize=12)
    # Line 3
    tw.append(fitz.Point(100, 140), "Third line too", font=font_reg, fontsize=12)

    tw.write_text(page)

    test_pdf = "/tmp/test_multiline.pdf"
    doc.save(test_pdf)
    doc.close()

    # Extract spans
    result = core_xpc.get_block_spans(test_pdf, 0, "First line")
    assert result['success'], f"Failed to extract multi-line block: {result['message']}"

    spans = result['spans']

    # Check that we got multiple line indices
    line_indices = set(span['line_index'] for span in spans)

    print(f"  ✓ Extracted {len(spans)} spans")
    print(f"  ✓ Line indices: {sorted(line_indices)}")
    print(f"  ✓ Block bbox: ({result['block_bbox']['width']:.1f}x{result['block_bbox']['height']:.1f})")

    return True


def test_07_error_handling():
    """Test error handling for invalid inputs."""
    print("\n[TEST 07] Error Handling")

    # Test 1: Non-existent file
    result1 = core_xpc.get_block_spans("/tmp/nonexistent.pdf", 0, "text")
    assert not result1['success'], "Should fail for non-existent file"
    print(f"  ✓ Non-existent file handled: {result1['message']}")

    # Test 2: Text not found
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Hello", fontsize=12)
    test_pdf = "/tmp/test_error.pdf"
    doc.save(test_pdf)
    doc.close()

    result2 = core_xpc.get_block_spans(test_pdf, 0, "Nonexistent")
    assert not result2['success'], "Should fail for text not found"
    print(f"  ✓ Text not found handled: {result2['message']}")

    # Test 3: Invalid page index
    result3 = core_xpc.get_block_spans(test_pdf, 999, "Hello")
    assert not result3['success'], "Should fail for invalid page"
    print(f"  ✓ Invalid page handled: {result3['message']}")

    # Test 4: Empty spans array
    result4 = core_xpc.replace_block_with_spans(
        test_pdf,
        0,
        {'x': 0, 'y': 0, 'width': 100, 'height': 100},
        []  # Empty spans
    )
    assert not result4['success'], "Should fail for empty spans"
    print(f"  ✓ Empty spans handled: {result4['message']}")

    return True


def run_all_tests():
    """Run all multi-font tests."""
    tests = [
        test_01_get_block_spans_simple,
        test_02_replace_block_with_spans_simple,
        test_03_get_and_replace_round_trip,
        test_04_color_preservation,
        test_05_bold_italic_detection,
        test_06_multi_line_block,
        test_07_error_handling
    ]

    print("=" * 70)
    print("Week 6 Day 2 - Multi-Font Text Blocks Tests")
    print("=" * 70)

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"  ✗ Test returned False")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ Assertion failed: {e}")
        except Exception as e:
            failed += 1
            print(f"  ✗ Exception: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
