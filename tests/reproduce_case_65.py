import sys
import os
import fitz
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import core

def reproduce_case_65():
    input_pdf = " 2.pdf"
    output_pdf = "repro_case_65.pdf"
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
    
    print(f"Result: {res['success']}")
    print(f"Message: {res.get('message')}")
    if res.get('debug_log'):
        print("Debug Log:")
        for line in res['debug_log']:
            print(f"  {line}")

    if res['success']:
        # Check if text is actually in the PDF
        doc = fitz.open(output_pdf)
        page = doc[page_num-1]
        text = page.get_text()
        if replacement in text:
            print(f"SUCCESS: '{replacement}' found in output text.")
        else:
            print(f"FAILURE: '{replacement}' NOT found in output text.")
        doc.close()

if __name__ == "__main__":
    reproduce_case_65()
