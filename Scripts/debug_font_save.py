#!/usr/bin/env python3
"""
Debug script to verify font extraction and reinsertion.
Tests the exact flow used in replace_text_in_pdf.
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site'))

import fitz

def test_font_save(pdf_path: str, target_text: str, new_text: str, page_num: int = 1):
    """Test saving with extracted font."""
    
    print("=" * 60)
    print("FONT SAVE DEBUG TEST")
    print("=" * 60)
    print(f"PDF: {pdf_path}")
    print(f"Target: '{target_text}' -> '{new_text}'")
    print()
    
    # Open PDF
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    
    # Find text
    hits = page.search_for(target_text)
    if not hits:
        print("ERROR: Text not found")
        return
    rect = hits[0]
    print(f"Found text at: {rect}")
    
    # Get font info from spans
    blocks = page.get_text("dict")["blocks"]
    font_info = None
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if target_text in span.get("text", ""):
                    font_info = {
                        'fontname': span.get('font'),
                        'fontsize': span.get('size'),
                        'origin': (span.get('origin', (0, 0))),
                    }
                    break
    
    if not font_info:
        print("ERROR: Unable to identify font")
        return
        
    print(f"Font info: {font_info}")
    
    # Extract font to temp file
    fontname = font_info['fontname']
    target_clean = fontname.split('+')[-1].lower() if '+' in fontname else fontname.lower()
    extracted_path = None
    
    print(f"\nExtracting font matching '{fontname}' (clean: '{target_clean}')...")
    
    for f in page.get_fonts():
        xref, ext, type_, basefont, internal_name, enc = f
        base_clean = basefont.split('+')[-1].lower() if '+' in basefont else basefont.lower()
        
        if base_clean == target_clean or target_clean in base_clean:
            print(f"  Found matching font: xref={xref}, basefont={basefont}")
            font_data = doc.extract_font(xref)
            if font_data and len(font_data) > 3 and font_data[3]:
                # font_data[3] is the font binary data
                extracted_path = tempfile.NamedTemporaryFile(suffix='.ttf', delete=False).name
                with open(extracted_path, 'wb') as f:
                    f.write(font_data[3])
                print(f"  Extracted to: {extracted_path}")
                print(f"  Size: {len(font_data[3])} bytes")
                break
    
    if not extracted_path:
        print("ERROR: Could not extract font")
        return
    
    # Load font via fitz.Font
    print(f"\nLoading font with fitz.Font(fontfile='{extracted_path}')...")
    try:
        repl_font = fitz.Font(fontfile=extracted_path)
        print(f"  Font name: {repl_font.name}")
        print(f"  Is writable: {repl_font.is_writable}")
        print(f"  Has glyph for 'a': {repl_font.has_glyph(ord('a'))}")
        print(f"  Has glyph for 'n': {repl_font.has_glyph(ord('n'))}")
        print(f"  Buffer size: {len(repl_font.buffer) if repl_font.buffer else 0}")
    except Exception as e:
        print(f"  ERROR loading font: {e}")
        return
    
    # Apply redaction
    print(f"\nApplying redaction to rect {rect}...")
    page.add_redact_annot(rect, fill=(1, 1, 1))
    result = page.apply_redactions(images=0, graphics=1)
    print(f"  apply_redactions result: {result}")
    
    # Verify text was removed
    remaining = page.search_for(target_text)
    print(f"  Text still found after redaction: {len(remaining) > 0}")
    
    # Insert new text using font buffer
    print(f"\nInserting new text '{new_text}'...")
    insert_point = fitz.Point(rect.x0, rect.y1 - 3)  # Approximate baseline
    
    temp_name = "TestFont"
    try:
        page.insert_font(fontname=temp_name, fontbuffer=repl_font.buffer)
        print(f"  Registered font as '{temp_name}'")
    except Exception as e:
        print(f"  ERROR registering font: {e}")
        return
    
    try:
        page.insert_text(
            insert_point,
            new_text,
            fontname=temp_name,
            fontsize=font_info['fontsize'],
            color=(0, 0, 0)
        )
        print(f"  Text inserted at {insert_point}")
    except Exception as e:
        print(f"  ERROR inserting text: {e}")
        return
    
    # Save output
    output_path = pdf_path.replace('.pdf', '_font_debug.pdf')
    doc.save(output_path)
    print(f"\nSaved to: {output_path}")
    
    # Cleanup
    os.unlink(extracted_path)
    doc.close()
    
    print("\n" + "=" * 60)
    print("Open the output file and compare fonts!")
    print("=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 debug_font_save.py <pdf_path> <target_text> <new_text>")
        sys.exit(1)
    
    test_font_save(sys.argv[1], sys.argv[2], sys.argv[3])
