
import sys
sys.path.insert(0, 'Sources/Marcedit/python_site')
import fitz
import os

pdf_path = "ignored-resources/sample-files/billing-statement-invoice.pdf"
doc = fitz.open(pdf_path)
page = doc[0]

print(f"--- Analyzing Fonts in {os.path.basename(pdf_path)} ---")
fonts = page.get_fonts()

for f in fonts:
    xref, ext, type_, basefont, name, enc = f
    print(f"\nFont: {name} ({basefont}) XREF={xref} Type={type_}")
    
    # 1. Extract Buffer
    font_buffer = doc.extract_font(xref)
    if not font_buffer:
        print("  [!] No font buffer found (Standard 14?)")
        continue

    val = font_buffer[3]
    if not val:
        print("  [!] Buffer is empty")
        continue
        
    print(f"  Buffer Size: {len(val)} bytes")
    
    # 2. Check Glyphs
    test_str = "Testing123"
    temp_font = fitz.Font(fontbuffer=val)
    missing = []
    for char in test_str:
        if not temp_font.has_glyph(ord(char)):
            missing.append(char)
            
    if missing:
        print(f"  [!] Missing glyphs for '{test_str}': {missing}")
    else:
        print(f"  [OK] Has glyphs for '{test_str}'")

    # 3. Test Insert with Internal Name (Simulate 'Smart Reuse')
    # Use a fresh doc for each test to avoid side effects
    doc_a = fitz.open(pdf_path)
    page_a = doc_a[0]
    
    # Redact a small area to clear space (optional, just writing on top is fine for visibility check)
    # page_a.insert_text((100, 100 + fonts.index(f)*50), f"Reuse Name {name}: {test_str}", fontname=name, fontsize=12, color=(1,0,0))
    # Note: insert_text needs 'fontname' to be the key in page properties, usually 'name' from get_fonts() (e.g. 'F1')
    
    try:
        # We try to use the existing internal name 'name'
        # Check if we can just pass fontname=name. 
        # Actually page.insert_text(..., fontname=name) should work if name is registered.
        page_a.insert_text((50, 100 + fonts.index(f)*30), f"TEST NAME REUSE {name}: {test_str}", fontname=name, fontsize=12, color=(1,0,0))
        doc_a.save(f"debug_reuse_name_{name}.pdf")
        print(f"  Saved debug_reuse_name_{name}.pdf")
    except Exception as e:
        print(f"  [!] Reuse Name Failed: {e}")

    # 4. Test Insert with Extracted Buffer (Simulate 'Buffer Reuse')
    doc_b = fitz.open(pdf_path)
    page_b = doc_b[0]
    try:
        # Register new font with buffer
        new_font_name = f"new_{name}"
        # insert_font(fontname=..., fontbuffer=...) registers the font
        page_b.insert_font(fontname=new_font_name, fontbuffer=val)
        
        # Now insert text using that new name
        page_b.insert_text((50, 150 + fonts.index(f)*30), f"TEST BUFFER REUSE {name}: {test_str}", fontname=new_font_name, fontsize=12, color=(0,0,1))
        
        doc_b.save(f"debug_reuse_buffer_{name}.pdf")
        print(f"  Saved debug_reuse_buffer_{name}.pdf")
        
        # Check size difference
        sz_orig = os.path.getsize(pdf_path)
        sz_new = os.path.getsize(f"debug_reuse_buffer_{name}.pdf")
        print(f"  Size Delta: {sz_new - sz_orig} bytes")
        
    except Exception as e:
        print(f"  [!] Reuse Buffer Failed: {e}")

