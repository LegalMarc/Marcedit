
import fitz

def test_graphics_redaction():
    pdf_path = " 2.pdf"
    target = "Injury"
    page_num = 129
    
    print(f"Testing Redaction on '{target}' (Page {page_num})...")
    
    # Test 1: graphics=0 (Current behavior)
    doc1 = fitz.open(pdf_path)
    page1 = doc1[page_num-1]
    rects1 = page1.search_for(target)
    if not rects1:
        print("Target not found.")
        return
        
    print(f"Found {len(rects1)} instances.")
    for r in rects1:
        page1.add_redact_annot(r, fill=(1, 0, 0)) # Red fill to see if it works
        
    page1.apply_redactions(images=0, graphics=0)
    
    # Check if text remains
    hits1 = page1.search_for(target)
    print(f"Test 1 (graphics=0): Remaining hits = {len(hits1)}")
    if len(hits1) > 0:
        print("  FAILED to remove text with graphics=0")
    else:
        print("  SUCCESS removing text with graphics=0")
        
    doc1.save("debug_redact_g0.pdf")
    doc1.close()
    
    # Test 2: graphics=1
    doc2 = fitz.open(pdf_path)
    page2 = doc2[page_num-1]
    rects2 = page2.search_for(target)
    
    for r in rects2:
        page2.add_redact_annot(r, fill=(0, 1, 0)) # Green fill
        
    page2.apply_redactions(images=0, graphics=1) # Enable graphics removal
    
    hits2 = page2.search_for(target)
    print(f"Test 2 (graphics=1): Remaining hits = {len(hits2)}")
    if len(hits2) > 0:
        print("  FAILED to remove text with graphics=1")
    else:
        print("  SUCCESS removing text with graphics=1")
        
    doc2.save("debug_redact_g1.pdf")
    doc2.close()

if __name__ == "__main__":
    test_graphics_redaction()
