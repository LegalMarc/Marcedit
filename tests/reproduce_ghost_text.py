
import fitz
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "Sources/Marcedit/python_site"))
from editor_pkg import core

def test_ghost_text():
    pdf_path = " 2.pdf"
    target = "Injury"
    replacement = "Verified"
    page_num = 129
    
    print(f"Analyzing '{target}' -> '{replacement}' on page {page_num} of {pdf_path}...")
    
    # 1. Inspect ALL spans on the page
    doc = fitz.open(pdf_path)
    page = doc[page_num-1]
    
    print("\n--- ALL SPANS NEAR TARGET ---")
    blocks = page.get_text("dict")["blocks"]
    for b in blocks:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                # Search for any span containing 'Injury' OR 'Liability' OR near the target rect
                rect = fitz.Rect(s['bbox'])
                if "Injury" in s['text'] or "Liability" in s['text'] or rect.y0 > 200 and rect.y1 < 300:
                    print(f"Span: '{s['text']}'")
                    print(f"  BBox: {s['bbox']}")
                    print(f"  Font: {s['font']}, Size: {s['size']:.1f}, Flags: {s['flags']}")
    
    rects = page.search_for(target)
    print(f"\nSearch found {len(rects)} instances of '{target}'")
    for r in rects:
        print(f"  Rect: {r}")
        
    doc.close()
    
    # 2. Run Replacement
    output_path = "debug_ghost.pdf"
    print("\nRunning Replacement...")
    res = core.replace_text_in_pdf(
        input_path=pdf_path,
        output_path=output_path,
        page_number=page_num,
        target_text=target,
        replacement_text=replacement
    )
    
    print(f"\nResult: {res['success']}")
    print("Debug Logs:")
    for l in res.get('debug_log', []):
        print(l)
        
    # 3. Post-verification
    if res['success']:
        doc_out = fitz.open(output_path)
        page_out = doc_out[page_num-1]
        
        # Check if Target is gone
        remaining = page_out.search_for(target)
        print(f"\nPost-Verification:")
        print(f"  Target '{target}' search hits: {len(remaining)} (Should be 0)")
        
        # Check if Replacement is present
        new_hits = page_out.search_for(replacement)
        print(f"  Replacement '{replacement}' search hits: {len(new_hits)} (Should be > 0)")
        
        doc_out.close()

if __name__ == "__main__":
    test_ghost_text()
