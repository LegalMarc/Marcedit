#!/usr/bin/env python3
"""Debug script to investigate the AllAndNone font glyph issue."""
import sys
sys.path.insert(0, 'Sources/Marcedit/python_site')
import fitz

pdf_path = "ignored-resources/sample-files/Foreign Package Policy.pdf"

print(f"=== Analyzing: {pdf_path} ===")

doc = fitz.open(pdf_path)
page = doc[0]

# 1. Find all fonts on page
print("=== All Fonts on Page ===")
fonts = page.get_fonts()
for f in fonts:
    xref, ext, type_, basefont, internal_name, enc = f
    print(f"  {internal_name}: {basefont} (xref={xref}, type={type_}, enc={enc})")
print()

# 2. Check AllAndNone font specifically
print("=== AllAndNone Font Analysis ===")
for f in fonts:
    xref, ext, type_, basefont, internal_name, enc = f
    if 'allandnone' in basefont.lower():
        print(f"Found: {internal_name}: {basefont}")
        font_data = doc.extract_font(xref)
        if font_data and len(font_data) >= 4:
            print(f"  Font data fields: {len(font_data)}")
            print(f"  Name: {font_data[0]}")
            print(f"  Ext: {font_data[1]}")
            print(f"  Type: {font_data[2]}")
            
            buffer = font_data[3]
            if buffer:
                print(f"  Buffer size: {len(buffer)} bytes")
                
                try:
                    temp_font = fitz.Font(fontbuffer=buffer)
                    print(f"  Font name from buffer: {temp_font.name}")
                    
                    # Check specific characters
                    test_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                    available = []
                    missing = []
                    for c in test_chars:
                        result = temp_font.has_glyph(ord(c))
                        if result:
                            available.append(c)
                        else:
                            missing.append(c)
                    
                    print(f"  Available chars: {''.join(available)}")
                    print(f"  Missing chars: {''.join(missing) if missing else 'None'}")
                    
                    # Specific check for O and U
                    print(f"  has_glyph('O'): {temp_font.has_glyph(ord('O'))}")
                    print(f"  has_glyph('U'): {temp_font.has_glyph(ord('U'))}")
                except Exception as e:
                    print(f"  FAILED to create font from buffer: {e}")
            else:
                print(f"  NO BUFFER!")
        else:
            print("  No font data extracted!")
print()

# 3. Find where COMMERCIAL text is and what font it uses
print("=== Finding COMMERCIAL text ===")
blocks = page.get_text("dict")["blocks"]
for block in blocks:
    if "lines" in block:
        for line in block["lines"]:
            for span in line["spans"]:
                if "COMMERCIAL" in span["text"]:
                    print(f"  Found: '{span['text']}'")
                    print(f"  Font: {span['font']}")
                    print(f"  Size: {span['size']}")
                    print()
                if "INSURANCE" in span["text"]:
                    print(f"  Found: '{span['text']}'")
                    print(f"  Font: {span['font']}")
                    print(f"  Size: {span['size']}")
                    print()
