#!/usr/bin/env python3
import pathlib
import subprocess
import shutil
from analyze_results import analyze

SAMPLE_DIR = pathlib.Path(__file__).parent / "ignored-resources" / "sample-files"
EDITED_DIR = pathlib.Path("/tmp/pdf_edits")
REPORT_PATH = pathlib.Path("/tmp/pdf_edit_report.md")

try:
    import fitz
except ImportError:
    pass


def render_page(pdf_path: str, page: int, out_stem: str):
    # Use fitz (PyMuPDF) to render a single page to PNG
    # out_stem should act like the stem, but we will force .png extension
    # if out_stem doesn't end with .png, add it.
    
    out_png = str(out_stem)
    if not out_png.endswith(".png"):
        out_png += ".png"
        
    try:
        doc = fitz.open(pdf_path)
        if page < len(doc):
            pix = doc[page].get_pixmap()
            pix.save(out_png)
    except Exception as e:
        print(f"Error rendering {pdf_path}: {e}")


def generate():
    print("Running analysis...")
    analysis_results = analyze()
    
    print(f"Generating report at {REPORT_PATH}...")
    
    with open(REPORT_PATH, "w") as report:
        report.write("# PDF Editing Master Report\n\n")
        
        # Summary Section
        report.write("## Summary\n\n")
        report.write("| File | Structure Warnings | Visual Metric |\n")
        report.write("|---|---|---|\n")
        
        for fname, data in analysis_results.items():
            warnings = "<br>".join(data["structure"]) if data["structure"] else "OK"
            visual = data["visual"]
            report.write(f"| {fname} | {warnings} | {visual} |\n")
            
        report.write("\n---\n\n")
        
        # Detailed Visuals
        for pdf_file in SAMPLE_DIR.glob("*.pdf"):
            edited = EDITED_DIR / pdf_file.name
            if not edited.exists():
                continue
            
            report.write(f"## {pdf_file.name}\n\n")
            
            data = analysis_results.get(pdf_file.name, {})
            if data.get("structure"):
                report.write("> [!WARNING]\n")
                report.write(f"> **Structure Issues**: {', '.join(data['structure'])}\n\n")
                
            report.write(f"**Visual Check result**: {data.get('visual', 'N/A')}\n\n")
            
            # Show first page visual comparison
            try:
                orig_png = f"/tmp/{pdf_file.stem}_orig_0.png"
                edit_png = f"/tmp/{pdf_file.stem}_edit_0.png"
                
                # Render using the helper which expects full path for png output?
                # pdftoppm appends .png so we pass stem
                render_page(pdf_file, 0, f"/tmp/{pdf_file.stem}_orig_0")
                render_page(edited, 0, f"/tmp/{pdf_file.stem}_edit_0")
                
                report.write(f"| Original | Edited |\n")
                report.write(f"|---|---|\n")
                report.write(f"| ![]({orig_png}) | ![]({edit_png}) |\n\n")
                
            except Exception as e:
                report.write(f"> Error rendering preview: {e}\n\n")
                
            report.write("---\n\n")

    print("Report generation complete.")

if __name__ == "__main__":
    generate()
