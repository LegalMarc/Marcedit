import fitz
import sys
import os
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import reflow

def create_superscript_pdf(filename="type_test.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    
    # Draw "Reference[1]"
    # Base text
    page.insert_text((50, 100), "Reference", fontsize=12, fontname="helv")
    
    # Superscript "1"
    # Baseline shifted UP (smaller Y)
    # x approx 50 + width of Reference (~55)
    page.insert_text((110, 96), "1", fontsize=8, fontname="helv")
    
    doc.save(filename)
    return filename

def run_tests():
    print("Running Typography/Baseline Tests...")
    input_pdf = create_superscript_pdf()
    
    doc = fitz.open(input_pdf)
    page = doc[0]
    
    # Find the "1"
    # We know approx location from creation
    target_rect = fitz.Rect(110, 88, 116, 98) # Tight box around "1"
    
    # Info for replacement
    font_info = {
        'fontname': 'helv',
        'fontsize': 8,
        'color': (0,0,0)
    }
    
    debug_log = []
    print("Attempting to replace Superscript '1' with '2'...")
    
    # Perform Reflow
    success, rect = reflow.reflow_line(page, target_rect, "2", font_info, debug_log)
    
    if success:
        print("PASS: Reflow successful.")
    else:
        print("FAIL: Reflow failed.")
        print(debug_log)
        return

    # Check Debug Log for Baseline Detection
    baseline_msg = [l for l in debug_log if "Using detected baseline" in l]
    if baseline_msg:
        print(f"PASS: {baseline_msg[0]}")
    else:
        print("FAIL: Did not detect baseline from spans.")
        print(debug_log)
        
    doc.save("type_output.pdf")
    if os.path.exists(input_pdf): os.remove(input_pdf)

if __name__ == "__main__":
    run_tests()
