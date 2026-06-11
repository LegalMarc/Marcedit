import sys
import os
import fitz

# Ensure python_site is in path
sys.path.insert(0, os.path.abspath("Sources/Marcedit/python_site"))
from editor_pkg import core

SAMPLE_DIR = "ignored-resources/sample-files-marcedit"

CASES = [
    {
        "id": "10",
        "pdf": "billing-statement-invoice-orig2.pdf",
        "page": 2, # 1-based
        "target": "also",
        "replacement": "Code",
        "desc": "Blue Text Check"
    },
    {
        "id": "12",
        "pdf": " 2 copy.pdf",
        "page": 16,
        "target": "INFORMATION",
        "replacement": "Confirmed",
        "desc": "Line Reflow Check"
    },
    {
        "id": "32",
        "pdf": " 2.pdf",
        "page": 151,
        "target": "with",
        "replacement": "Fix",
        "desc": "Vertical Hairline Check"
    },
    {
        "id": "41",
        "pdf": "Delaware Certificate of Merger.pdf",
        "page": 1,
        "target": "CONSULTING",
        "replacement": "Privileged and Confidential Material",
        "desc": "Font Regression Check"
    },
    {
        "id": "42",
        "pdf": "Delaware Certificate of Merger.pdf",
        "page": 1,
        "target": "First",
        "replacement": "Replacement",
        "desc": "Bad Font Check"
    }
]

def run_repro():
    print(f"Listing {SAMPLE_DIR}:")
    try:
        print(os.listdir(SAMPLE_DIR))
    except Exception as e:
        print(f"Error listing dir: {e}")

    for case in CASES:
        pdf_path = os.path.join(SAMPLE_DIR, case["pdf"])
        if not os.path.exists(pdf_path):
            print(f"Skipping Case {case['id']}: {pdf_path} not found.")
            continue
            
        print(f"\n--- Running Case {case['id']}: {case['desc']} ---")
        output_path = f"repro_case_{case['id']}.pdf"
        
        try:
            res = core.replace_text_in_pdf(
                input_path=pdf_path,
                output_path=output_path,
                page_number=case["page"],
                target_text=case["target"],
                replacement_text=case["replacement"]
            )
            print(f"Result: {res.get('success')}")
            if 'debug_log' in res:
                print("--- DEBUG LOG ---")
                for line in res['debug_log']:
                    print(line)
                print("--- END LOG ---")
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    run_repro()
