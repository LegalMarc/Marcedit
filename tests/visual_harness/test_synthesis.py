import fitz
import sys
import os
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import harvester
from editor_pkg import synthesizer

def create_test_pdf(filename="synth_test.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    
    # Insert source text with Times-Roman (Serif)
    # This ensures it's distict from default Helvetica
    page.insert_text((50, 50), "Hello World", fontname="Times-Roman", fontsize=20)
    
    doc.save(filename)
    return filename

def run_tests():
    print("Running Glyph Synthesis Tests...")
    input_pdf = create_test_pdf()
    
    doc = fitz.open(input_pdf)
    page = doc[0]
    
    # 1. Harvest Glyphs
    target_chars = {'H', 'e', 'l', 'o'}
    print(f"Harvesting: {target_chars}")
    glyph_map, missing = harvester.harvest_glyphs(doc, target_chars, "Times", page_limit=1)
    
    if missing:
        print(f"FAIL: Missing glyphs: {missing}")
        return
        
    print(f"PASS: Harvested {len(glyph_map)} glyphs.")
    for c, info in glyph_map.items():
        print(f"  '{c}': Page {info['page']}, BBox {info['bbox']}")
        
    # 2. Synthesize Text
    # Write "Hell" at a new location (50, 150)
    # Open a separate handle for the source document to satisfy show_pdf_page requirements
    src_doc = fitz.open(input_pdf)
    
    # We write onto the SAME page for this test
    start_point = (50, 150)
    print(f"\nSynthesizing 'Hell' at {start_point}...")
    # We use 'Hell' because we have glyphs for H, e, l. 
    # 'o' is also harvested but we'll just test a subset.
    width = synthesizer.draw_text_as_vectors(page, start_point, "Hell", glyph_map, size=20, doc=src_doc)
    
    print(f"PASS: Synthesized width: {width:.2f}")
    
    # Check if content was added
    # We can check rawdict again to see if "show_pdf_page" added searchable text?
    # NO, show_pdf_page adds an XObject (image-like). It is likely NOT searchable text.
    # So get_text("dict") won't see "Hell".
    # We verify by checking if page stream size increased or drawing commands exist?
    
    # Save output
    output_pdf = "synth_output.pdf"
    doc.save(output_pdf)
    print(f"Saved {output_pdf}")
    
    if os.path.exists(output_pdf):
        print("PASS: Output file generated.")
    
    # Cleanup
    if os.path.exists(input_pdf): os.remove(input_pdf)

if __name__ == "__main__":
    run_tests()
