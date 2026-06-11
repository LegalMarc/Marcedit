#!/usr/bin/env python3
import sys
import pathlib
import subprocess
import shutil

# Add bundled python_site to path
sys.path.insert(0, 'Sources/Marcedit/python_site')

try:
    import pikepdf
    import fitz
except ImportError:
    pass

SAMPLE_DIR = pathlib.Path(__file__).parent / "ignored-resources" / "sample-files"
OUTPUT_DIR = pathlib.Path("/tmp/pdf_edits")

def check_structure(orig_path, edited_path):
    """
    Check if important structural elements (like font resources) are preserved.
    Returns a list of warnings.
    """
    warnings = []
    try:
        orig = pikepdf.open(orig_path)
        edited = pikepdf.open(edited_path)
        
        # Simple check: Compare number of pages
        if len(orig.pages) != len(edited.pages):
            warnings.append(f"Page count mismatch: {len(orig.pages)} vs {len(edited.pages)}")
            return warnings
            
        # Check resources on first page
        p1_orig = orig.pages[0]
        p1_edit = edited.pages[0]
        
        if "/Font" in p1_orig.resources and "/Font" in p1_edit.resources:
            fonts_orig = set(p1_orig.resources["/Font"].keys())
            fonts_edit = set(p1_edit.resources["/Font"].keys())
            if not fonts_orig.issubset(fonts_edit):
                 warnings.append(f"Missing fonts in edited version: {fonts_orig - fonts_edit}")
        
    except Exception as e:
        warnings.append(f"Structure check failed: {e}")
        
    return warnings

def check_visual(orig_path, edited_path, page_idx=0):
    """
    Use fitz (PyMuPDF) to render pages and imagemagick to compare.
    Returns a diff metric or warning string. 
    """
    stem = orig_path.stem
    orig_png = f"/tmp/{stem}_orig.png"
    edit_png = f"/tmp/{stem}_edit.png"
    
    try:
        doc_orig = fitz.open(orig_path)
        doc_edit = fitz.open(edited_path)
        
        if page_idx >= len(doc_orig) or page_idx >= len(doc_edit):
            return "Page index out of range"
            
        pix_orig = doc_orig[page_idx].get_pixmap()
        pix_edit = doc_edit[page_idx].get_pixmap()
        
        pix_orig.save(orig_png)
        pix_edit.save(edit_png)
                       
        # If ImageMagick compare is available
        if shutil.which("compare"):
            diff_png = f"/tmp/{stem}_diff.png"
            # compare -metric AE orig.png edit.png diff.png
            res = subprocess.run(["compare", "-metric", "AE", orig_png, edit_png, diff_png],
                                 capture_output=True, text=True)
            # compare writes metric to stderr usually
            metric = res.stderr.strip()
            return f"Pixel diff: {metric}"
        else:
            return "ImageMagick 'compare' not found"
            
    except Exception as e:
        return f"Rendering failed: {e}"

def analyze():
    results = {}
    
    for pdf_file in SAMPLE_DIR.glob("*.pdf"):
        edited = OUTPUT_DIR / pdf_file.name
        if not edited.exists():
            continue
            
        print(f"Analyzing {pdf_file.name}...")
        
        struct_warns = check_structure(pdf_file, edited)
        visual_res = check_visual(pdf_file, edited)
        
        results[pdf_file.name] = {
            "structure": struct_warns,
            "visual": visual_res
        }
        
    return results

if __name__ == "__main__":
    res = analyze()
    for fname, data in res.items():
        print(f"File: {fname}")
        if data["structure"]:
            print(f"  Structure Warnings: {data['structure']}")
        print(f"  Visual Check: {data['visual']}")
