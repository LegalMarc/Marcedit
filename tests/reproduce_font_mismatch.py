
import fitz
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "Sources/Marcedit/python_site"))
from editor_pkg import core

def test_font_mismatch():
    pdf_path = " 2.pdf"
    target = "COMMON"
    replacement = "$1, 000"
    page_num = 1 # From screenshot, looks like page 1 (or 10 based on log snippet "p10")
    
    # User screenshot says "Case #34... Source: 2.pdf p10"
    page_num = 10 
    
    print(f"Analyzing font for '{target}' on page {page_num} of {pdf_path}...")
    
    # 1. Inspect PDF font info directly
    doc = fitz.open(pdf_path)
    page = doc[page_num-1]
    
    # Search text
    rects = page.search_for(target)
    if not rects:
        print(f"Target '{target}' not found on page {page_num}")
        return
        
    rect = rects[0]
    print(f"Target found at: {rect}")
    
    # Get direct font name from PyMuPDF
    # text_page = page.get_textpage() 
    # extractDICT gives us font names
    blocks = page.get_text("dict")["blocks"]
    for b in blocks:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if target in s["text"]:
                    print(f"Direct Span Info: Font='{s['font']}', Size={s['size']}, Color={s['color']}")
                    print(f"  Flags: {s['flags']}")
    
    doc.close()
    
    # 2. Run core.identify_font
    print("\nRunning core.identify_font...")
    font_info = core.identify_font(pdf_path, page_num, target)
    print(f"Identified Font Info: {font_info}")
    
    # 3. Run replacement and check logs
    print("\nRunning replacement...")
    res = core.replace_text_in_pdf(
        input_path=pdf_path, 
        output_path="debug_font_mismatch.pdf", 
        page_number=page_num, 
        target_text=target, 
        replacement_text=replacement
    )
    
    print("\nDebug Log:")
    for line in res.get('debug_log', []):
        print(line)

if __name__ == "__main__":
    test_font_mismatch()
