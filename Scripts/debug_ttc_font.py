#!/usr/bin/env python3
"""
Debug script to test TTC font insertion directly with PyMuPDF.
Run this from the Marcedit directory with the bundled Python.
"""

import fitz
import os

def test_ttc_font_insertion():
    """Test inserting a specific font from a TTC collection."""
    
    # Test font: Bangla MN Bold from TTC
    font_path = "/System/Library/Fonts/Supplemental/Bangla MN.ttc"
    ps_name = "BanglaMN-Bold"
    
    if not os.path.exists(font_path):
        print(f"Font not found: {font_path}")
        return
    
    print(f"Testing TTC font: {font_path}")
    print(f"Target PS name: {ps_name}")
    print()
    
    # Step 1: Probe the TTC to find the correct index
    ps_target = ps_name.replace('-', '').replace(' ', '').lower()
    found_idx = None
    
    print("Probing TTC indices...")
    for i in range(10):
        try:
            with fitz.open() as temp_doc:
                temp_page = temp_doc.new_page()
                xref = temp_page.insert_font(fontname=f"probe_{i}", fontfile=font_path, idx=i)
                for font_item in temp_page.get_fonts():
                    if font_item[0] == xref:
                        font_name = font_item[3]
                        tf_name = font_name.replace('-', '').replace(' ', '').lower()
                        match = "✓ MATCH" if tf_name == ps_target else ""
                        print(f"  Index {i}: {font_name} (normalized: {tf_name}) {match}")
                        if tf_name == ps_target:
                            found_idx = i
                            break
            if found_idx is not None:
                break
        except Exception as e:
            print(f"  Index {i}: Error - {e}")
            break
    
    print()
    
    if found_idx is None:
        print("Could not find matching font in TTC!")
        print("Falling back to index 0...")
        found_idx = 0
    
    # Step 2: Create a test PDF and insert text with the font
    print(f"Creating test PDF with font index {found_idx}...")
    
    doc = fitz.open()
    page = doc.new_page()
    
    # Insert the font
    temp_name = "TestFont"
    try:
        xref = page.insert_font(fontname=temp_name, fontfile=font_path, idx=found_idx)
        print(f"Font inserted successfully, xref={xref}")
    except Exception as e:
        print(f"Failed to insert font: {e}")
        return
    
    # Insert text
    test_text = "Hello World - Testing TTC Font"
    insert_point = fitz.Point(50, 100)
    fontsize = 24
    
    try:
        page.insert_text(insert_point, test_text, fontname=temp_name, fontsize=fontsize, color=(0, 0, 0))
        print(f"Text inserted successfully")
    except Exception as e:
        print(f"Failed to insert text: {e}")
        return
    
    # Save the PDF
    output_path = "/tmp/ttc_font_test.pdf"
    doc.save(output_path)
    doc.close()
    
    print(f"\nTest PDF saved to: {output_path}")
    print("Open this file to verify the font appears correctly.")

if __name__ == "__main__":
    print("PyMuPDF version:", fitz.__version__)
    print()
    test_ttc_font_insertion()
