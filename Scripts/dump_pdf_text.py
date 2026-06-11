#!/usr/bin/env python3
"""
Diagnostic script to dump PDF content stream text.
Run: python3 dump_pdf_text.py /path/to/file.pdf [page_number]
"""
import sys
sys.path.insert(0, '/Users/mhm/Documents/Dev/Marcedit/Sources/Marcedit/python_site')

import pikepdf
from pikepdf import Operator

def dump_text(pdf_path, page_num=1):
    print(f"Opening: {pdf_path}")
    print(f"Page: {page_num}")
    print("-" * 60)
    
    with pikepdf.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        commands = pikepdf.parse_content_stream(page)
        
        text_count = 0
        for operands, operator in commands:
            if operator == Operator("Tj"):
                text_obj = operands[0]
                text_str = str(text_obj)
                text_bytes = bytes(text_obj) if hasattr(text_obj, '__bytes__') else b'?'
                print(f"Tj: str='{text_str}' bytes={text_bytes[:50]!r}")
                text_count += 1
                
            elif operator == Operator("TJ"):
                chunks = []
                for item in operands[0]:
                    if isinstance(item, (str, pikepdf.String)):
                        chunks.append(str(item))
                full = "".join(chunks)
                print(f"TJ: '{full}' ({len(chunks)} chunks)")
                text_count += 1
        
        print("-" * 60)
        print(f"Total text operators: {text_count}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 dump_pdf_text.py /path/to/file.pdf [page_number]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    dump_text(pdf_path, page_num)
