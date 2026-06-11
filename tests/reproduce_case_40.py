
import fitz
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "Sources/Marcedit/python_site"))
from editor_pkg import core, visual_matcher

def test_case_40():
    pdf_path = " 2.pdf"
    target = "your"
    replacement = "Log"
    page_num = 4 
    
    print(f"Analyzing font for '{target}' on page {page_num} of {pdf_path}...")
    
    doc = fitz.open(pdf_path)
    page = doc[page_num-1]
    
    # 1. Inspect direct font info
    rects = page.search_for(target)
    if not rects:
        print("Target not found.")
        return
    rect = rects[0]
    
    print(f"Rect: {rect}")
    
    # Get font name from span
    font_name = ""
    blocks = page.get_text("dict")["blocks"]
    for b in blocks:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if target in s["text"]:
                    font_name = s["font"]
                    print(f"Original Text Span: '{s['text']}'")
                    print(f"  FontName: {s['font']}")
                    print(f"  Flags: {s['flags']}")
                    print(f"  Size: {s['size']}")
                    break
    
    # 2. Run Detect Serif Visually
    print("\nRunning Visual Serif Detection...")
    matcher = visual_matcher.VisualFontMatcher()
    is_serif = matcher.detect_serif_visually(page, target, font_name)
    print(f"  Visual Serif Detection Result: {is_serif}")
    
    # 3. Test find_matching_font with penalty
    print("\nRunning Matching Font Search...")
    match = visual_matcher.find_matching_font(
        page, target, font_name, 
        src_is_serif=is_serif,
        exhaustive=False 
    )
    print(f"  Best Match: {match}")
    
    # 4. Run Full Replacement to see logs
    print("\nRunning Full Replacement...")
    res = core.replace_text_in_pdf(
        input_path=pdf_path,
        output_path="debug_case_40.pdf",
        page_number=page_num,
        target_text=target,
        replacement_text=replacement
    )
    print("\nDebug Logs:")
    for l in res.get('debug_log', []):
        print(l)

if __name__ == "__main__":
    test_case_40()
