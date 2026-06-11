
import fitz
import sys
import os

def analyze_redline_pdf(path):
    print(f"Analyzing '{path}'...")
    try:
        doc = fitz.open(path)
    except Exception as e:
        print(f"Could not open file: {e}")
        return

    # Look for the text "services provider selected by Rudin" (from screenshot)
    target_text = "services provider selected by Rudin"
    
    found = False
    for page in doc:
        text_instances = page.search_for(target_text)
        if text_instances:
            print(f"Found on Page {page.number + 1}")
            found = True
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block["type"] == 0: # text
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if target_text in span["text"] or "provider selected" in span["text"]:
                                print(f"SPAN: text='{span['text']}'")
                                print(f"      font='{span['font']}'")
                                print(f"      flags={span['flags']} (is_bold={span['flags'] & 16 != 0}, is_italic={span['flags'] & 2 != 0})")
                                print(f"      size={span['size']}")
                                print(f"-" * 40)
    
    if not found:
        print(f"Text '{target_text}' not found in '{path}'")

if __name__ == "__main__":
    # The file path in the screenshot is "Redline - Fitness Center Term Sheet.pdf"
    # It might be in sample-files or elsewhere. I'll check sample-files first.
    paths = [
        "ignored-resources/sample-files/Redline - Fitness Center Term Sheet.pdf",
        "Redline - Fitness Center Term Sheet.pdf"
    ]
    
    for p in paths:
        if os.path.exists(p):
            analyze_redline_pdf(p)
            break
    else:
        print("File not found in expected locations.")
