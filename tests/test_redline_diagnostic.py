#!/usr/bin/env python3
"""
Redline Color Corruption Diagnostic Test

This script performs a detailed analysis of the red text corruption issue in redline documents.
It captures comprehensive diagnostic data to understand why replacement text appears in red
despite hardcoded black color values.

Test case: Edit "Investor" → "Investor" in redline PDF
Expected: All black text
Actual: Random red letters (b, v, p)

Diagnostic data collected:
1. Font selection (visual matcher score, path, name)
2. Color values at every stage
3. Text rendering mode
4. Content stream before/after replacement
5. Graphics state analysis
"""

import sys
import os
import json
import tempfile
from pathlib import Path

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site')
sys.path.insert(0, python_site)

import fitz  # PyMuPDF
from editor_pkg import core


def analyze_content_stream_colors(page, rect):
    """
    Analyze the content stream to find color operators in the region.

    Returns dict with:
    - color_operators: List of (operator, values) tuples
    - render_mode_operators: List of Tr values found
    - text_objects: Count of BT...ET blocks
    """
    try:
        # Read content stream
        stream_bytes = page.read_contents()
        stream_str = stream_bytes.decode('latin-1')  # PDF uses latin-1 encoding

        results = {
            'color_operators': [],
            'render_mode_operators': [],
            'text_objects': 0,
            'stream_length': len(stream_bytes),
            'sample': stream_str[:500] + '...' if len(stream_str) > 500 else stream_str
        }

        # Parse for color operators
        # RGB fill: "r g b rg"
        # RGB stroke: "r g b RG"
        # Gray fill: "g g"
        # Gray stroke: "g G"
        # CMYK: "c m y k k"
        # Render mode: "mode Tr"

        lines = stream_str.split('\n')
        for line in lines:
            tokens = line.strip().split()
            if not tokens:
                continue

            # Check last token for operator
            op = tokens[-1]

            if op == 'rg' and len(tokens) == 4:  # RGB fill color
                r, g, b = float(tokens[0]), float(tokens[1]), float(tokens[2])
                results['color_operators'].append(('rg_fill', (r, g, b)))

            elif op == 'RG' and len(tokens) == 4:  # RGB stroke color
                r, g, b = float(tokens[0]), float(tokens[1]), float(tokens[2])
                results['color_operators'].append(('RG_stroke', (r, g, b)))

            elif op == 'g' and len(tokens) == 2:  # Gray fill
                gray = float(tokens[0])
                results['color_operators'].append(('g_fill', gray))

            elif op == 'G' and len(tokens) == 2:  # Gray stroke
                gray = float(tokens[0])
                results['color_operators'].append(('G_stroke', gray))

            elif op == 'k' and len(tokens) == 5:  # CMYK
                c, m, y, k = float(tokens[0]), float(tokens[1]), float(tokens[2]), float(tokens[3])
                results['color_operators'].append(('k_cmyk', (c, m, y, k)))

            elif op == 'Tr' and len(tokens) == 2:  # Text render mode
                mode = int(tokens[0])
                results['render_mode_operators'].append(mode)

            elif op == 'BT':  # Begin text object
                results['text_objects'] += 1

        return results

    except Exception as e:
        return {'error': str(e)}


def analyze_pdf_text_color(pdf_path, search_text, page_num=0):
    """
    Analyze color information for specific text in PDF.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num]

    # Find the text
    search_results = page.search_for(search_text)
    if not search_results:
        return {'error': f'Text "{search_text}" not found on page {page_num + 1}'}

    rect = search_results[0]

    # Get text dict for color info
    text_dict = page.get_text('dict', clip=rect + (-2, -2, 2, 2))

    span_info = []
    for block in text_dict.get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                color_int = span.get('color', 0)
                r = ((color_int >> 16) & 0xFF) / 255.0
                g = ((color_int >> 8) & 0xFF) / 255.0
                b = (color_int & 0xFF) / 255.0

                span_info.append({
                    'text': span.get('text', ''),
                    'font': span.get('font', ''),
                    'size': span.get('size', 0),
                    'color_int': color_int,
                    'color_rgb': (r, g, b),
                    'flags': span.get('flags', 0)
                })

    doc.close()

    return {
        'rect': tuple(rect),
        'spans': span_info
    }


def run_diagnostic_edit(pdf_path, original_text, replacement_text, page_num):
    """
    Perform an edit with comprehensive diagnostic logging.
    """
    print(f"\n{'='*70}")
    print(f"DIAGNOSTIC EDIT TEST")
    print(f"{'='*70}")
    print(f"PDF: {os.path.basename(pdf_path)}")
    print(f"Page: {page_num}")
    print(f"Text: '{original_text}' → '{replacement_text}'")
    print()

    # Create temp output
    fd, output_path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)

    try:
        # BEFORE: Analyze original
        print("📊 BEFORE EDIT:")
        print("-" * 70)

        before_analysis = analyze_pdf_text_color(pdf_path, original_text, page_num - 1)
        print(f"Original text location: {before_analysis.get('rect')}")
        print(f"Spans found: {len(before_analysis.get('spans', []))}")

        for i, span in enumerate(before_analysis.get('spans', [])):
            print(f"  Span {i+1}: '{span['text'][:30]}'")
            print(f"    Font: {span['font']}")
            print(f"    Size: {span['size']:.1f}")
            print(f"    Color: RGB{span['color_rgb']} (int: {span['color_int']})")

        # Content stream BEFORE
        doc = fitz.open(pdf_path)
        page = doc[page_num - 1]
        search_results = page.search_for(original_text)
        if search_results:
            rect = search_results[0]
            stream_before = analyze_content_stream_colors(page, rect)
            print(f"\n  Content stream colors BEFORE:")
            for op, vals in stream_before.get('color_operators', []):
                print(f"    {op}: {vals}")
            print(f"  Render modes: {stream_before.get('render_mode_operators', [])}")
            print(f"  Text objects: {stream_before.get('text_objects', 0)}")
        doc.close()

        # PERFORM EDIT
        print(f"\n{'='*70}")
        print("🔧 PERFORMING EDIT...")
        print("-" * 70)

        result = core.replace_text_in_pdf(
            input_path=pdf_path,
            output_path=output_path,
            target_text=original_text,
            replacement_text=replacement_text,
            page_number=page_num
        )

        print(f"Success: {result.get('success')}")
        print(f"Message: {result.get('message')}")

        # Print debug log
        if result.get('debug_log'):
            print(f"\n📝 DEBUG LOG ({len(result['debug_log'])} entries):")
            print("-" * 70)
            for entry in result['debug_log']:
                print(f"  {entry}")

        if not result.get('success'):
            print(f"\n❌ Edit failed: {result.get('message')}")
            return None

        # AFTER: Analyze result
        print(f"\n{'='*70}")
        print("📊 AFTER EDIT:")
        print("-" * 70)

        after_analysis = analyze_pdf_text_color(output_path, replacement_text, page_num - 1)
        print(f"Replacement text location: {after_analysis.get('rect')}")
        print(f"Spans found: {len(after_analysis.get('spans', []))}")

        for i, span in enumerate(after_analysis.get('spans', [])):
            print(f"  Span {i+1}: '{span['text'][:30]}'")
            print(f"    Font: {span['font']}")
            print(f"    Size: {span['size']:.1f}")
            print(f"    Color: RGB{span['color_rgb']} (int: {span['color_int']})")

            # Check for red contamination
            r, g, b = span['color_rgb']
            if r > 0.5 and g < 0.3 and b < 0.3:
                print(f"    ⚠️  RED TEXT DETECTED!")

        # Content stream AFTER
        doc = fitz.open(output_path)
        page = doc[page_num - 1]
        search_results = page.search_for(replacement_text)
        if search_results:
            rect = search_results[0]
            stream_after = analyze_content_stream_colors(page, rect)
            print(f"\n  Content stream colors AFTER:")
            for op, vals in stream_after.get('color_operators', []):
                print(f"    {op}: {vals}")
            print(f"  Render modes: {stream_after.get('render_mode_operators', [])}")
            print(f"  Text objects: {stream_after.get('text_objects', 0)}")
        doc.close()

        # ANALYSIS
        print(f"\n{'='*70}")
        print("🔍 ANALYSIS:")
        print("-" * 70)

        # Check if color changed
        before_colors = [s['color_rgb'] for s in before_analysis.get('spans', [])]
        after_colors = [s['color_rgb'] for s in after_analysis.get('spans', [])]

        print(f"Before colors: {before_colors}")
        print(f"After colors: {after_colors}")

        # Check for red in output
        has_red = any(r > 0.5 and g < 0.3 and b < 0.3 for r, g, b in after_colors)

        if has_red:
            print(f"\n❌ RED TEXT DETECTED IN OUTPUT!")
            print(f"   This confirms the bug is still present.")
        else:
            print(f"\n✅ No red text detected - all colors are correct!")

        # Save diagnostic report
        report = {
            'test': {
                'pdf': os.path.basename(pdf_path),
                'page': page_num,
                'original': original_text,
                'replacement': replacement_text
            },
            'before': before_analysis,
            'after': after_analysis,
            'result': result,
            'has_red_contamination': has_red
        }

        _ignored = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ignored-resources")
        os.makedirs(_ignored, exist_ok=True)
        report_path = os.path.join(_ignored, 'diagnostic_report.json')
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n📄 Full report saved to: {report_path}")
        print(f"📄 Output PDF saved to: {output_path}")

        return output_path

    except Exception as e:
        print(f"\n❌ DIAGNOSTIC TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run comprehensive diagnostic tests."""

    # Test PDF
    pdf_path = "ignored-resources/sample-files-marcedit/Redline - Energize Holdings, Inc. - Management Rights Letter (BlueCo) (Sidley Draft 9.11.2025)-v1 and Management Rights Letter_EnergizeBlueCo-v2.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ Test PDF not found: {pdf_path}")
        return 1

    print(f"\n{'='*70}")
    print(f"REDLINE COLOR CORRUPTION DIAGNOSTIC")
    print(f"{'='*70}")
    print(f"\nGoal: Understand why replacement text appears in red")
    print(f"Method: Detailed analysis of content stream and color operators")
    print()

    # Test case 1: "Investor" → "Investor"
    print(f"\n{'#'*70}")
    print(f"TEST CASE 1: Same-text replacement (stress test)")
    print(f"{'#'*70}")

    output = run_diagnostic_edit(
        pdf_path=pdf_path,
        original_text="Investor",
        replacement_text="Investor",
        page_num=1
    )

    if output:
        print(f"\n✅ Diagnostic complete - review output PDF and JSON report")
        print(f"\nNext steps:")
        print(f"1. Review diagnostic_report.json for detailed analysis")
        print(f"2. Open {output} to visually confirm red text issue")
        print(f"3. Check debug log for font selection and color values")
        print(f"4. Analyze content stream operators before/after")

    return 0


if __name__ == "__main__":
    sys.exit(main())
