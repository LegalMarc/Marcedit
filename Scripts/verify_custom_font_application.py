
import sys
import os
import fitz

# Setup path to import core
sys.path.insert(0, '/Users/mhm/Documents/Dev/Marcedit/Sources/Marcedit/python_site')
from editor_pkg import core

TEST_PDF = "test_custom_font.pdf"
TARGET_TEXT = "ReplaceMe"

def create_test_pdf():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), f"This is a {TARGET_TEXT} text.", fontsize=12, fontname="helv", color=(0,0,0))
    doc.save(TEST_PDF)
    print(f"[Setup] Created {TEST_PDF}")

def verify_font_application(override_font, expected_basefont_substring):
    print(f"\n[Test] Applying Custom Font: {override_font}")
    
    # 1. Apply Replacement
    overrides = {
        'manual_font': override_font
    }
    
    # Call core function
    output_path = f"output_{override_font.replace(' ', '_').replace('|', '_')}.pdf"
    result = core.replace_text_in_pdf(
        input_path=TEST_PDF,
        output_path=output_path,
        target_text=TARGET_TEXT,
        replacement_text="NewValue",
        page_number=1,
        manual_overrides=overrides
    )
    
    if not result['success']:
        print(f"  [FAIL] Replacement failed: {result['message']}")
        return False
        
    # 2. Verify Result
    # output_path is already defined above
    doc = fitz.open(output_path)
    page = doc[0]
    
    # Find the "NewValue" text and check its font
    text_dict = page.get_text("dict")
    found = False
    actual_font = "Unknown"
    
    for block in text_dict["blocks"]:
        if "lines" not in block: continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "NewValue" in span["text"]:
                    found = True
                    actual_font = span["font"]
                    break
    
    print(f"  [Check] Found text 'NewValue' with font: {actual_font}")
    
    # Check for match or known aliases (Nimbus is often used for Courier/Times/Helv on Linux/OSS)
    match = False
    expect = expected_basefont_substring.lower()
    actual = actual_font.lower()
    
    if expect in actual: match = True
    elif "courier" in expect and "nimbusmono" in actual: match = True
    elif "times" in expect and "nimbusroman" in actual: match = True
    elif "helve" in expect and ("nimbus" in actual or "arial" in actual): match = True
    
    if match:
        print(f"  [PASS] Font matched expectation: {expected_basefont_substring} (mapped to {actual_font})")
        return True
    else:
        print(f"  [FAIL] Expected font containing '{expected_basefont_substring}', but got '{actual_font}'")
        return False

def main():
    create_test_pdf()
    
    # Test 1: Courier
    # In PyMuPDF/core.py mapping: "Courier" -> "Courier"
    if not verify_font_application("Courier", "Courier"):
        sys.exit(1)
        
    # Test 2: Times
    # In PyMuPDF/core.py mapping: "Times" -> "Times-Roman" or "Times"
    if not verify_font_application("Times-Roman", "Times"):
        sys.exit(1)
        
    # Test 3: Helvetica-Bold
    if not verify_font_application("Helvetica-Bold", "Helvetica-Bold"):
        sys.exit(1)

    print("\n[Summary] All custom font tests PASSED.")

if __name__ == "__main__":
    main()
