#!/usr/bin/env python3
"""
Debug script to understand why redaction isn't removing text.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site'))

import fitz

def debug_redaction(pdf_path, target_text, page_num=1):
    """Debug redaction step by step."""
    
    print("=" * 60)
    print("REDACTION DEBUG")
    print("=" * 60)
    
    # Open PDF
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    
    # Find text
    rects = page.search_for(target_text)
    if not rects:
        print(f"Text '{target_text}' not found")
        return
    
    rect = rects[0]
    print(f"Found target text at: {rect}")
    
    # Check text extraction BEFORE
    print("\n--- TEXT EXTRACTION BEFORE REDACTION ---")
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if target_text in span.get("text", ""):
                    print(f"  BEFORE: '{span['text']}' at {span['bbox']}")
                    print(f"    Font: {span['font']}, size: {span['size']}")
    
    # Check raw content stream
    print("\n--- PAGE CONTENT STREAM (length) ---")
    xref = page.xref
    cont = page.read_contents()
    print(f"  Content stream length: {len(cont)} bytes")
    
    # Apply redaction
    print("\n--- APPLYING REDACTION ---")
    page.add_redact_annot(rect, fill=(1, 1, 1))
    result = page.apply_redactions(images=0, graphics=1)
    print(f"  apply_redactions result: {result}")
    
    # Check content stream AFTER
    print("\n--- PAGE CONTENT STREAM AFTER (length) ---")
    cont_after = page.read_contents()
    print(f"  Content stream length: {len(cont_after)} bytes")
    print(f"  Size change: {len(cont_after) - len(cont)} bytes")
    
    # Check text extraction AFTER
    print("\n--- TEXT EXTRACTION AFTER REDACTION ---")
    text_dict_after = page.get_text("dict")
    found_after = False
    for block in text_dict_after.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if target_text in span.get("text", ""):
                    found_after = True
                    print(f"  AFTER: '{span['text']}' at {span['bbox']}")
                    print(f"    Font: {span['font']}, size: {span['size']}")
    
    if not found_after:
        print("  (no text found matching target)")
    
    # Search AFTER
    print("\n--- SEARCH AFTER REDACTION ---")
    remaining = page.search_for(target_text)
    if remaining:
        print(f"  STILL FOUND: {remaining}")
    else:
        print("  NOT FOUND (good!)")
    
    # Save and reopen to verify persistence
    print("\n--- SAVE AND REOPEN ---")
    import tempfile
    out_path = tempfile.mktemp(suffix=".pdf")
    doc.save(out_path)
    doc.close()
    
    doc2 = fitz.open(out_path)
    page2 = doc2[page_num - 1]
    remaining2 = page2.search_for(target_text)
    print(f"  After save+reopen, search finds: {remaining2 if remaining2 else 'NOTHING (good!)'}")
    
    # Also check in the SAVED file
    print("\n--- TEXT EXTRACTION IN SAVED FILE ---")
    text_dict_saved = page2.get_text("dict")
    found_saved = False
    for block in text_dict_saved.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if target_text in span.get("text", ""):
                    found_saved = True
                    print(f"  SAVED: '{span['text']}' at {span['bbox']}")
    
    if not found_saved:
        print("  (no target text found in saved file)")
    
    doc2.close()
    os.unlink(out_path)
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    pdf_path = "ignored-resources/sample-files/billing-statement-invoice.pdf"
    target = "Contact Information"
    
    if len(sys.argv) >= 3:
        pdf_path = sys.argv[1]
        target = sys.argv[2]
    
    debug_redaction(pdf_path, target)
