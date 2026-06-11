
import fitz
import sys
import os
import plistlib

def analyze_pdf(path):
    print(f"Analyzing '{path}'...")
    doc = fitz.open(path)
    for page in doc:
        text_instances = page.search_for("A PAYMENT SCHEDULE")
        if text_instances:
            print(f"Found text on page {page.number}")
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block["type"] == 0: # text
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if "A PAYMENT SCHEDULE" in span["text"] or "PAYMENT" in span["text"]:
                                print(f"SPAN: text='{span['text']}' font='{span['font']}' size={span['size']} color={span['color']} flags={span['flags']}")
                                print(f"      origin={span['origin']} bbox={span['bbox']}")
    
    # Check "Where from" metadata
    try:
        import xattr
        try:
            # Try to get raw xattr
            # Note: The attribute name usually includes the prefix on listing valid keys, 
            # but xattr lib usage depends on OS.
            attr_name = "com.apple.metadata:kMDItemWhereFroms"
            val = xattr.getxattr(path, attr_name)
            print(f"\nRaw xattr '{attr_name}': {len(val)} bytes")
            try:
                # Decoding binary plist
                pl = plistlib.loads(val)
                print(f"Decoded Plist: {pl}")
            except Exception as e:
                print(f"Plist decoding failed: {e}")
        except Exception as e:
            print(f"xattr get failed: {e}")
            try:
                print(f"Available xattrs: {xattr.listxattr(path)}")
            except:
                pass
            
    except ImportError:
        print("xattr module not installed")

if __name__ == "__main__":
    analyze_pdf("ignored-resources/sample-files/ 2.pdf")
