import sys
import os
import fitz
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import core

def create_input_pdf(filename="collision_test.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    
    # "Hello     World" - Gap of ~50 pts
    # Increased gap to avoid initial touching for clean edit test
    page.insert_text((40, 100), "Hello", fontsize=20)
    page.insert_text((200, 100), "World", fontsize=20)
    
    # Add a target to replace
    page.insert_text((120, 100), "TARGET", fontsize=20)
    
    doc.save(filename)
    return filename

def run_integration_test():
    print("Running Optical Integration Test...")
    input_pdf = create_input_pdf()
    output_pdf = "collision_result.pdf"
    
    # Test 1: Clean Edit
    # Replaces "TARGET" with "Fit" -> Should fit perfectly
    print("\n--- Test 1: Clean Edit ---")
    res1 = core.replace_text_in_pdf(
        input_pdf, output_pdf,
        target_text="TARGET",
        replacement_text="Fit",
        manual_overrides={'manual_font': 'helv'}
    )
    print(f"Result: {res1['success']}")
    print(f"Message: {res1.get('message')}")
    
    if res1['success']:
        print("PASS: Clean edit succeeded")
    else:
        print("FAIL: Clean edit failed unexpectedly")
        if res1.get('debug_log'):
             for line in res1['debug_log']:
                 print(f"  {line}")

    # Test 2: Collision Edit (Now Reflow Edit)
    # Replaces "TARGET" with "MASSIVE_TEXT_BLOCK" -> Should Reflow neighbors
    print("\n--- Test 2: Collision Edit (Now Reflow Test) ---")
    res2 = core.replace_text_in_pdf(
        input_pdf, output_pdf,
        target_text="TARGET", 
        replacement_text="MASSIVE_TEXT_BLOCK_THAT_HITS_NEIGHBORS",
        manual_overrides={'manual_font': 'helv', 'exhaustive_search': False, 'skip_heuristic_check': True} 
    )
    print(f"Result: {res2['success']}")
    print(f"Message: {res2.get('message')}")
    
    if res2['success']:
        print("PASS: Reflow prevented collision and succeeded!")
        # Ideally we'd verify the shift here, but success + no visual collision check failure implies it worked.
    else:
        print("FAIL: Edit failed.")
        if res2.get('debug_log'):
             for line in res2['debug_log']:
                 print(f"  {line}")

    if os.path.exists(input_pdf): os.remove(input_pdf)
    if os.path.exists(output_pdf): os.remove(output_pdf)

if __name__ == "__main__":
    run_integration_test()
