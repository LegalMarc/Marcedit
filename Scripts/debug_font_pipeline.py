#!/usr/bin/env python3
"""
Debug script to test the font extraction pipeline.
Run from project root: python3 debug_font_pipeline.py /path/to/test.pdf "Target Text"
"""

import sys
import os

# Add the editor package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site'))

from editor_pkg import core
import fitz

def test_font_extraction(pdf_path: str, target_text: str, page_num: int = 1):
    """Test the entire font extraction pipeline."""
    
    print("=" * 60)
    print("FONT EXTRACTION PIPELINE DEBUG")
    print("=" * 60)
    print(f"PDF: {pdf_path}")
    print(f"Target: '{target_text}'")
    print(f"Page: {page_num}")
    print()
    
    # Step 1: Open PDF and find text
    print("[STEP 1] Opening PDF and searching for text...")
    with fitz.open(pdf_path) as doc:
        if page_num < 1 or page_num > len(doc):
            print(f"  ERROR: Invalid page number {page_num}")
            return
            
        page = doc[page_num - 1]
        
        # Search for text
        rect = core._robust_search(page, target_text)
        if not rect:
            print(f"  ERROR: Text '{target_text}' not found")
            return
        print(f"  Found at rect: {rect}")
        
        # Step 2: Get font info
        print("\n[STEP 2] Extracting font info...")
        font_info = core._get_span_font_info(page, target_text, rect)
        print(f"  fontname: {font_info.get('fontname')}")
        print(f"  fontsize: {font_info.get('fontsize')}")
        print(f"  flags: {font_info.get('flags')}")
        print(f"  origin: {font_info.get('origin')}")
        
        # Step 3: Try to extract the font
        print("\n[STEP 3] Extracting embedded font...")
        fontname = font_info.get('fontname')
        if fontname:
            preview_path = core._extract_font_to_temp(doc, page, fontname)
            if preview_path:
                print(f"  SUCCESS! Font extracted to: {preview_path}")
                print(f"  File exists: {os.path.exists(preview_path)}")
                print(f"  File size: {os.path.getsize(preview_path) if os.path.exists(preview_path) else 0} bytes")
                
                # Check file header (TTF/OTF magic bytes)
                with open(preview_path, 'rb') as f:
                    header = f.read(4)
                    if header == b'\x00\x01\x00\x00':
                        print(f"  Font type: TrueType (.ttf)")
                    elif header == b'OTTO':
                        print(f"  Font type: OpenType/CFF (.otf)")
                    elif header == b'true':
                        print(f"  Font type: TrueType (true)")
                    else:
                        print(f"  Font header: {header.hex()}")
            else:
                print(f"  FAILED: Could not extract font '{fontname}'")
                
                # Debug: List all fonts on page
                print("\n  Available fonts on page:")
                for f in page.get_fonts():
                    xref, ext, type_, basefont, internal_name, enc = f
                    print(f"    xref={xref}, basefont={basefont}, ext={ext}, type={type_}")
        else:
            print(f"  ERROR: No fontname in font_info")
    
    # Step 4: Test identify_font function
    print("\n[STEP 4] Testing identify_font()...")
    result = core.identify_font(pdf_path, page_num, target_text)
    print(f"  success: {result.get('success')}")
    print(f"  fontname: {result.get('fontname')}")
    print(f"  fontsize: {result.get('fontsize')}")
    print(f"  preview_font_path: {result.get('preview_font_path')}")
    
    # Step 5: Test find_font_interactive generator
    print("\n[STEP 5] Testing find_font_interactive()...")
    for update in core.find_font_interactive(pdf_path, page_num - 1, target_text, exhaustive=False):
        print(f"  Update type: {update.get('type')}")
        if update.get('type') == 'complete':
            print(f"  success: {update.get('success')}")
            best = update.get('best_match', {})
            print(f"  best_match.name: {best.get('name')}")
            print(f"  best_match.path: {best.get('path')}")
            print(f"  best_match.score: {best.get('score')}")
            print(f"  source: {update.get('source')}")
            
            # THIS IS CRITICAL - check if path is the extracted temp file
            path = best.get('path')
            if path and path.startswith('/tmp/marcedit_preview'):
                print(f"  ✓ SUCCESS: Path is extracted temp font")
            elif path == 'internal':
                print(f"  ✗ ISSUE: Path is 'internal' - font was NOT extracted")
            else:
                print(f"  ✗ ISSUE: Unexpected path format")
        elif update.get('type') == 'progress':
            pass  # Skip progress updates
    
    print("\n" + "=" * 60)
    print("DEBUG COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 debug_font_pipeline.py <pdf_path> <target_text> [page_num]")
        print("Example: python3 debug_font_pipeline.py test.pdf 'Contact Information' 1")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    target_text = sys.argv[2]
    page_num = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    test_font_extraction(pdf_path, target_text, page_num)
