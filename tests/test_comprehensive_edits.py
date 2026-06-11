#!/usr/bin/env python3
"""
Comprehensive PDF Editing Test Script

This script tests the ACTUAL application's editor_pkg.core module,
not the experimental pikepdf scripts. It runs a variety of edits
against the sample files and collects detailed results.
"""
import sys
import os
import pathlib
import json
import tempfile
import shutil

# Add the real application's python_site
sys.path.insert(0, '/Users/mhm/Documents/Dev/Marcedit/Sources/Marcedit/python_site')

try:
    from editor_pkg import core
    import fitz
except ImportError as e:
    print(f"ERROR: Failed to import editor_pkg or fitz: {e}")
    sys.exit(1)

SAMPLE_DIR = pathlib.Path("/Users/mhm/Documents/Dev/Marcedit/ignored-resources/sample-files")
OUTPUT_DIR = pathlib.Path("/tmp/marcedit_test_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Test cases: (description, target_text, replacement_text, page_number)
# These will be applied to each PDF where the target text is found
TEST_CASES = [
    # Simple word replacements
    ("Simple word: Company", "Company", "Acme Corp", 1),
    ("Simple word: Invoice", "Invoice", "Receipt", 1),
    
    # Numeric replacements (dates, amounts)
    ("Date replacement", "2025", "2026", 1),
    ("Amount replacement", "$1,488.00", "$2,500.00", 1),
    
    # Multi-word (potential mid-line)
    ("Multi-word", "Term Sheet", "Agreement", 1),
    
    # Table cell content
    ("Table cell", "Minimum Due", "Amount Owed", 1),
    
    # Legal entity (tests cross-column issue from prior conversation)
    ("Legal entity", "Delaware", "California", 1),
]


def run_test(pdf_path: pathlib.Path, target: str, replacement: str, page: int) -> dict:
    """Run a single replacement test and return results."""
    result = {
        "file": pdf_path.name,
        "target": target,
        "replacement": replacement,
        "page": page,
        "success": False,
        "message": "",
        "debug_log": [],
        "font_source": None,
        "visual_diff": None
    }
    
    # Create temp output file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        out_path = tmp.name
    
    try:
        # Call the REAL replace_text_in_pdf
        response = core.replace_text_in_pdf(
            input_path=str(pdf_path),
            output_path=out_path,
            target_text=target,
            replacement_text=replacement,
            page_number=page
        )
        
        result["success"] = response.get("success", False)
        result["message"] = response.get("message", "")
        result["debug_log"] = response.get("debug_log", [])
        result["font_source"] = response.get("applied_info", {}).get("font_source", "Unknown")
        
        # Verify the replacement exists in output
        if result["success"] and os.path.exists(out_path):
            with fitz.open(out_path) as doc:
                page_obj = doc[page - 1]
                text = page_obj.get_text()
                if replacement in text:
                    result["verified"] = True
                elif target not in text:
                    result["verified"] = True  # Target gone, replacement might be styled differently
                else:
                    result["verified"] = False
                    result["message"] += " | WARNING: Replacement text not found in output"
            
            # Visual diff (optional - requires fitz rendering)
            try:
                with fitz.open(str(pdf_path)) as orig_doc:
                    orig_pix = orig_doc[page - 1].get_pixmap()
                    orig_pix.save(f"/tmp/test_orig_{pdf_path.stem}_{page}.png")
                
                with fitz.open(out_path) as edit_doc:
                    edit_pix = edit_doc[page - 1].get_pixmap()
                    edit_pix.save(f"/tmp/test_edit_{pdf_path.stem}_{page}.png")
                    
                result["visual_diff"] = "Rendered"
            except Exception as ve:
                result["visual_diff"] = f"Error: {ve}"
                
    except Exception as e:
        result["message"] = f"Exception: {e}"
    finally:
        # Cleanup
        if os.path.exists(out_path):
            try:
                shutil.copy(out_path, OUTPUT_DIR / f"{pdf_path.stem}_{target[:10].replace(' ', '_')}.pdf")
            except:
                pass
            os.unlink(out_path)
    
    return result


def main():
    all_results = []
    
    print(f"Testing against {len(list(SAMPLE_DIR.glob('*.pdf')))} PDFs")
    print(f"Output directory: {OUTPUT_DIR}")
    print("-" * 60)
    
    for pdf_file in SAMPLE_DIR.glob("*.pdf"):
        print(f"\n=== {pdf_file.name} ===")
        
        for desc, target, replacement, page in TEST_CASES:
            print(f"  Testing: {desc}...", end=" ")
            
            result = run_test(pdf_file, target, replacement, page)
            all_results.append(result)
            
            if result["success"]:
                print(f"✓ ({result.get('font_source', 'N/A')})")
            else:
                print(f"✗ ({result['message'][:50]})")
    
    # Write JSON results
    results_file = OUTPUT_DIR / "test_results.json"
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)
    
    # Summary
    print("\n" + "=" * 60)
    successes = sum(1 for r in all_results if r["success"])
    verified = sum(1 for r in all_results if r.get("verified"))
    total = len(all_results)
    
    print(f"SUMMARY: {successes}/{total} replacements succeeded, {verified} verified")
    print(f"Results saved to: {results_file}")
    
    # Group failures by reason
    failures = [r for r in all_results if not r["success"]]
    if failures:
        print("\nFailure Analysis:")
        reasons = {}
        for f in failures:
            msg = f["message"]
            if "Text not found" in msg:
                key = "Text not found"
            elif "Exception" in msg:
                key = "Exception"
            else:
                key = msg[:30]
            reasons[key] = reasons.get(key, 0) + 1
        
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {count}x: {reason}")


if __name__ == "__main__":
    main()
