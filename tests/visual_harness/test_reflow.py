import fitz
import sys
import os
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import reflow

def create_test_pdf(filename="reflow_test.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    
    # "Hello World" - Single line
    page.insert_text((100, 100), "Hello", fontsize=20)
    page.insert_text((160, 100), "World", fontsize=20) # 60 unit gap+width
    
    doc.save(filename)
    return filename

def run_tests():
    print("Running Reflow Engine Tests...")
    input_pdf = create_test_pdf()
    
    # Test 1: Expansion (Hello -> Greetings)
    print("\n--- Test 1: Expansion ---")
    doc = fitz.open(input_pdf)
    page = doc[0]
    
    # Target "Hello"
    # Identify rect: approx (100, 80, 150, 105)
    target_rect = fitz.Rect(100, 80, 150, 105)
    
    font_info = {'fontname': 'helv', 'fontsize': 20, 'color': (0,0,0)}
    debug_log = []
    
    success = reflow.reflow_line(page, target_rect, "Greetings", font_info, debug_log)
    
    if success:
        print("PASS: Reflow reported success")
        print("\n".join(debug_log))
    else:
        print("FAIL: Reflow failed")
        print("\n".join(debug_log))
        return

    # Check result
    text_dict = page.get_text("dict")
    # We expect "Greetings" at x=100
    # We expect "World" to be shifted RIGHT (x > 160)
    
    greetings_found = False
    world_pos = None
    
    for b in text_dict["blocks"]:
        for l in b["lines"]:
            for s in l["spans"]:
                if "Greetings" in s['text']:
                    greetings_found = True
                if "World" in s['text']:
                    world_pos = s['origin'][0]
                    
    if greetings_found:
        print("PASS: Replacement text found")
    else:
        print("FAIL: Replacement text 'Greetings' not found")
        
    if world_pos and world_pos > 165:
        print(f"PASS: Suffix 'World' moved right (x={world_pos:.2f})")
    else:
        print(f"FAIL: Suffix 'World' did not move right enough (x={world_pos}). Original was ~160.")
        
    doc.close()

    # Test 2: Contraction (Hello -> Hi)
    print("\n--- Test 2: Contraction ---")
    doc = fitz.open(input_pdf)
    page = doc[0]
    
    target_rect = fitz.Rect(100, 80, 150, 105)
    font_info = {'fontname': 'helv', 'fontsize': 20, 'color': (0,0,0)}
    
    reflow.reflow_line(page, target_rect, "Hi", font_info)
    
    text_dict = page.get_text("dict")
    
    hi_found = False
    world_pos = None
    
    for b in text_dict["blocks"]:
        for l in b["lines"]:
            for s in l["spans"]:
                if "Hi" in s['text']:
                    hi_found = True
                if "World" in s['text']:
                    world_pos = s['origin'][0]
                    
    if hi_found:
        print("PASS: Replacement text found")
        
    if world_pos and world_pos < 155:
        print(f"PASS: Suffix 'World' moved left (x={world_pos:.2f})")
    else:
        print(f"FAIL: Suffix 'World' did not move left enough (x={world_pos}). Original was ~160.")
        
    if os.path.exists(input_pdf): os.remove(input_pdf)

if __name__ == "__main__":
    run_tests()
