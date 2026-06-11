import fitz
import sys
import os
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import reflow

def create_caps_pdf(filename="caps_test.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "ATTENTION", fontsize=12, fontname="helv", color=(0,0,0))
    doc.save(filename)
    return filename

def run_tests():
    print("Running Small Caps / Auto-Upper Tests...")
    input_pdf = create_caps_pdf()
    
    doc = fitz.open(input_pdf)
    page = doc[0]
    
    target_rect = fitz.Rect(50, 90, 150, 105) # "ATTENTION"
    
    font_info = {'fontname': 'helv', 'fontsize': 12, 'color': (0,0,0)}
    debug_log = []
    
    # Input Mixed Case
    replacement = "Warning"
    
    print(f"Replacing 'ATTENTION' with '{replacement}'...")
    success, rect = reflow.reflow_line(page, target_rect, replacement, font_info, debug_log)
    
    if not success:
        print("FAIL: Reflow failed")
        return
        
    # Check Debug Log
    msg = [l for l in debug_log if "Auto-converting replacement to UPPER" in l]
    if msg:
        print(f"PASS: {msg[0]}")
    else:
        print("FAIL: Auto-conversion did not trigger.")
        print(debug_log)
        
    # Verify Content in PDF?
    # Cannot easily grep text because we inserted it via Reflow... 
    # But if we search text, we should find "WARNING" not "Warning".
    
    text = page.get_text("text")
    if "WARNING" in text:
        print("PASS: PDF contains 'WARNING'")
    elif "Warning" in text:
        print("FAIL: PDF contains 'Warning'")
    else:
        print(f"WARN: Could not find content? Text: {text}")

    doc.save("caps_output.pdf")
    if os.path.exists(input_pdf): os.remove(input_pdf)

if __name__ == "__main__":
    run_tests()
