#!/usr/bin/env python3
"""Debug script to investigate the font glyph issue."""
import sys
sys.path.insert(0, 'Sources/Marcedit/python_site')
import fitz

pdf_path = "ignored-resources/sample-files/billing-statement-invoice.pdf"
target_text = "COMMERCIAL"
replacement_text = "CUMMERCIAL"  # O -> U

print(f"=== Analyzing: {pdf_path} ===")
print(f"Target: '{target_text}' -> '{replacement_text}'")
print()

doc = fitz.open(pdf_path)
page = doc[0]

# 1. Find all fonts on page
print("=== All Fonts on Page ===")
fonts = page.get_fonts()
for f in fonts:
    xref, ext, type_, basefont, internal_name, enc = f
    print(f"  {internal_name}: {basefont} (xref={xref}, type={type_})")
print()

# 2. Find actual font used for "COMMERCIAL" text
print(f"=== Font used for '{target_text}' ===")
blocks = page.get_text("dict")["blocks"]
for block in blocks:
    if "lines" in block:
        for line in block["lines"]:
            for span in line["spans"]:
                if target_text in span["text"]:
                    print(f"  Found in span: '{span['text']}'")
                    print(f"  Font: {span['font']}")
                    print(f"  Size: {span['size']}")
                    print(f"  Flags: {span['flags']}")
                    print()
print()

# 3. Check each font for 'U' glyph
print("=== Glyph Check for 'U' (ord=85) ===")
for f in fonts:
    xref, ext, type_, basefont, internal_name, enc = f
    font_data = doc.extract_font(xref)
    if font_data and len(font_data) >= 4 and font_data[3]:
        buffer = font_data[3]
        try:
            temp_font = fitz.Font(fontbuffer=buffer)
            has_u = temp_font.has_glyph(ord('U'))
            print(f"  {internal_name} ({basefont}): has 'U' = {has_u}, buffer size = {len(buffer)}")
        except Exception as e:
            print(f"  {internal_name} ({basefont}): FAILED to load - {e}")
    else:
        print(f"  {internal_name} ({basefont}): No buffer (Standard 14 or reference)")
print()

# 4. Check what the matching logic does
print("=== Font Matching Simulation ===")
font_name = "AllAndNone"  # From the error message
target_base = font_name.split('+')[-1].lower() if '+' in font_name else font_name.lower()
print(f"Looking for font matching: '{target_base}'")

for f in fonts:
    xref, ext, type_, basefont, internal_name, enc = f
    font_base = basefont.split('+')[-1].lower() if '+' in basefont else basefont.lower()
    
    if font_base == target_base or target_base in font_base:
        print(f"  MATCH: {internal_name} ({basefont})")
        font_data = doc.extract_font(xref)
        if font_data and len(font_data) >= 4 and font_data[3]:
            buffer = font_data[3]
            temp_font = fitz.Font(fontbuffer=buffer)
            has_u = temp_font.has_glyph(ord('U'))
            print(f"    Has 'U': {has_u}")
            print(f"    Buffer size: {len(buffer)} bytes")
        else:
            print(f"    NO BUFFER - This would trigger fallback!")
    else:
        print(f"  No match: {internal_name} ({basefont})")
