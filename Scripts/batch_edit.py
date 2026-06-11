#!/usr/bin/env python3
import sys
import pathlib

# Add bundled python_site to path
sys.path.insert(0, '/Users/mhm/Documents/Dev/Marcedit/Sources/Marcedit/python_site')

try:
    import pikepdf
except ImportError:
    print("Error: Could not import pikepdf. Ensure the sys.path is correct.")
    sys.exit(1)

from pdf_editor import load_pdf, save_pdf, replace_text

SAMPLE_DIR = pathlib.Path(__file__).parent / "ignored-resources" / "sample-files"
OUTPUT_DIR = pathlib.Path("/tmp/pdf_edits")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Define some test replacements to exercise different scenarios
RULES = [
    # (pattern, replacement, description)
    (r"Company", "Acme Corp", "Simple word replacement"),
    (r"Section \d+", "Section X", "Regex replacement"),
    (r"\d{4}", "YYYY", "Number replacement"),
]

def run_batch():
    stats = {"processed": 0, "edited": 0, "errors": 0}
    
    print(f"Starting batch processing of PDFs in {SAMPLE_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    
    files = list(SAMPLE_DIR.glob("*.pdf"))
    if not files:
        print("No PDF files found in sample directory.")
        return

    for pdf_path in files:
        stats["processed"] += 1
        print(f"Processing {pdf_path.name}...")
        
        try:
            pdf = load_pdf(str(pdf_path))
            total_replacements = 0
            
            for i in range(len(pdf.pages)):
                for pattern, repl, _ in RULES:
                    count = replace_text(pdf, i, pattern, repl)
                    total_replacements += count
            
            if total_replacements > 0:
                out_path = OUTPUT_DIR / pdf_path.name
                save_pdf(pdf, str(out_path))
                print(f"  -> Saved to {out_path.name} ({total_replacements} replacements)")
                stats["edited"] += 1
            else:
                print("  -> No matches found, skipping save.")
                
        except Exception as e:
            print(f"  -> ERROR: {e}")
            stats["errors"] += 1

    print("-" * 40)
    print(f"Batch complete. Processed: {stats['processed']}, Edited: {stats['edited']}, Errors: {stats['errors']}")

if __name__ == "__main__":
    run_batch()
