import sys
import os
import fitz
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import core

def reproduce_case_65():
    input_pdf = " 2.pdf"
    output_pdf = "repro_case_65_v2.pdf"
    target = "THIRD"
    replacement = "Standard"
    page_num = 8
    
    if not os.path.exists(input_pdf):
        print(f"Error: {input_pdf} not found")
        return

    print(f"Reproducing Case #65: '{target}' -> '{replacement}' in {input_pdf} p{page_num}")
    
    res = core.replace_text_in_pdf(
        input_path=input_pdf,
        output_path=output_pdf,
        page_number=page_num,
        target_text=target,
        replacement_text=replacement
    )
    
    print(f"Success: {res['success']}")
    
    if res['success']:
        doc = fitz.open(output_pdf)
        page = doc[page_num-1]
        text = page.get_text()
        
        words = [w[4] for w in page.get_text("words")]
        print(f"Words found on page: {words[:50]}...") # Print first 50 words
        
        # We expect neighboring words to be present
        if replacement in words:
            print(f"PASS: Replacement '{replacement}' found.")
        else:
            print(f"FAIL: Replacement '{replacement}' NOT found in words list.")
            
        if "AVENUE" in words:
            print("PASS: Neighbor 'AVENUE' preserved.")
        else:
            print("FAIL: Neighbor 'AVENUE' was REDACTED (blooming error).")
            
        if "777" in words:
            print("PASS: Neighbor '777' preserved.")
        else:
            print("FAIL: Neighbor '777' was REDACTED (blooming error).")

        # Check visual position (rough check)
        # Find 'Standard' word rect
        for w in page.get_text("words"):
            if w[4] == replacement:
                print(f"'{replacement}' insertion rect: {fitz.Rect(w[:4])}")
                # We expect X to be around 149 (from previous logs)
                if 140 < w[0] < 160:
                    print("PASS: Insertion X coordinate looks correct.")
                else:
                    print(f"FAIL: Insertion X coordinate is {w[0]}, expected ~149.")
                break
        
        doc.close()

if __name__ == "__main__":
    reproduce_case_65()
