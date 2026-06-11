import sys
import os
import fitz

# Setup path
sys.path.insert(0, "./Sources/Marcedit/python_site")
from editor_pkg import core

def test_edit():
    pdf_path = "ignored-resources/sample-files/Redline - Fitness Center Term Sheet.pdf"
    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        return

    _ignored = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ignored-resources")
    os.makedirs(_ignored, exist_ok=True)
    output_path = os.path.join(_ignored, "temp_test_output.pdf")
    
    target = "ACTIVE 710643250v13"
    repl = "ACTIVE 710643250v13" # Identity
    
    print(f"Editing {pdf_path}...")
    try:
        res = core.replace_text_in_pdf(
            input_path=pdf_path,
            output_path=output_path,
            target_text=target,
            replacement_text=repl,
            page_number=1
        )
        
        print(f"Success: {res.get('success')}")
        print(f"Font Source: {res.get('font_source')}")
        print(f"Final Font: {res.get('applied_info', {}).get('final_font')}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_edit()
