import fitz
import sys
import os
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import reflow

def create_watermark_pdf(filename="watermark_test.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    
    # 1. Draw Watermark (Gray Rect)
    # Covering 50,50 to 200,100
    page.draw_rect((40, 40, 300, 150), color=(0.8, 0.8, 0.8), fill=(0.8, 0.8, 0.8))
    
    # 2. Draw Text ON TOP
    page.insert_text((50, 100), "CONFIDENTIAL DATA", fontsize=20, fontname="helv", color=(0,0,0))
    
    doc.save(filename)
    return filename

def run_tests():
    print("Running Watermark Safety Tests...")
    input_pdf = create_watermark_pdf()
    
    doc = fitz.open(input_pdf)
    page = doc[0]
    
    # Define replacement region (The text)
    target_rect = fitz.Rect(50, 82, 260, 105)
    
    # Count paths BEFORE
    paths_before = len(page.get_drawings())
    print(f"Paths Before: {paths_before}") # Should be 1 (the rect)
    
    # Perform Reflow (with transparent redaction)
    font_info = {'fontname': 'helv', 'fontsize': 20, 'color': (0,0,0)}
    debug_log = []
    
    print("Replacing 'CONFIDENTIAL DATA' with 'SAFE'...")
    success, rect = reflow.reflow_line(page, target_rect, "SAFE", font_info, debug_log)
    
    if not success:
        print("FAIL: Reflow failed")
        print(debug_log)
        return
        
    # VERIFY
    # 1. Check paths. If we used fill=(1,1,1), we'd expect +1 path (the white box).
    # If fill=None, we expect SAME number of paths (just the watermark).
    # Actually, apply_redactions might merge/change things, but adding a white box definitely adds a path.
    
    paths_after = len(page.get_drawings())
    print(f"Paths After: {paths_after}")
    
    path_delta = paths_after - paths_before
    
    if path_delta == 0:
        print("PASS: No new paths added (Watermark preserved, no white box).")
    elif path_delta > 0:
        # Check if the new path is white?
        drawings = page.get_drawings()
        last_path = drawings[-1]
        if last_path['fill'] == (1,1,1):
            print("FAIL: White box added over watermark!")
        else:
            print(f"WARN: Paths changed by {path_delta}, but might not be white box.")
            
    doc.save("watermark_output.pdf")
    if os.path.exists(input_pdf): os.remove(input_pdf)

if __name__ == "__main__":
    run_tests()
