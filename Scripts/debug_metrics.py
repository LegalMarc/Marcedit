
import sys
import fitz

pdf_path = 'ignored-resources/sample-files/billing-statement-invoice.pdf'
font_name_fragment = "Calibri"

print(f"PyMuPDF Version: {fitz.version}")
doc = fitz.open(pdf_path)
page = doc[0]

fonts = page.get_fonts()
target_xref = 0

for f in fonts:
    xref, ext, type, basefont, name, encoding = f
    if font_name_fragment in basefont:
        target_xref = xref
        break

if not target_xref:
    print("Xref not found")
    sys.exit(1)

print(f"Target xref: {target_xref}")

try:
    print("Calling doc.extract_font(target_xref)...")
    res = doc.extract_font(target_xref)
    if res is None:
        print("extract_font returned None")
    else:
        name, ext, flags, buffer = res
        print(f"Extracted: name={name}, ext={ext}, len={len(buffer)}")
        
        print("Creating fitz.Font(fontbuffer=buffer)...")
        font = fitz.Font(fontbuffer=buffer)
        print(f"SUCCESS! ascender={font.ascender}, descender={font.descender}")
except Exception as e:
    print(f"ERROR: {e}")
