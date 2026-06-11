#!/usr/bin/env python3
"""
Text Edit Test Harness

Comprehensive automated testing of the text replacement functionality
to diagnose issues where text disappears instead of being replaced.

This script simulates what the Swift app does and validates the results.
"""

import sys
import os
import tempfile
import shutil
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple

# Setup paths
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
PYTHON_SITE = PROJECT_ROOT / "Sources" / "Marcedit" / "python_site"
SAMPLE_FILES = PROJECT_ROOT / "ignored-resources" / "sample-files"

sys.path.insert(0, str(PYTHON_SITE))

import fitz
from editor_pkg import core


@dataclass
class TestCase:
    """A single test case for text replacement."""
    name: str
    pdf_path: str
    page_number: int
    target_text: str
    replacement_text: str
    overrides: Optional[dict] = None
    
    
@dataclass  
class TestResult:
    """Result of a single test case."""
    test_name: str
    passed: bool
    target_found_before: bool
    replacement_found_after: bool
    target_found_after: bool
    api_success: bool
    api_message: str
    error: Optional[str] = None
    debug_log: Optional[List[str]] = None


class TextEditTestHarness:
    """Automated test harness for text edit functionality."""
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results: List[TestResult] = []
        
    def log(self, msg: str, level: str = "INFO"):
        """Log a message if verbose mode is on."""
        if self.verbose:
            prefix = {"INFO": "ℹ️", "OK": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "")
            print(f"{prefix} {msg}")
    
    def find_test_pdfs(self) -> List[Path]:
        """Find all PDFs in sample files directory."""
        if not SAMPLE_FILES.exists():
            return []
        return list(SAMPLE_FILES.glob("*.pdf"))
    
    def analyze_pdf(self, pdf_path: Path) -> List[dict]:
        """Analyze a PDF to find editable text spans."""
        spans = []
        try:
            doc = fitz.open(str(pdf_path))
            for page_num in range(min(3, len(doc))):  # First 3 pages
                page = doc[page_num]
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text and len(text) >= 3 and len(text) <= 50:
                                spans.append({
                                    "text": text,
                                    "page": page_num + 1,
                                    "font": span.get("font", "Unknown"),
                                    "bbox": span.get("bbox"),
                                })
            doc.close()
        except Exception as e:
            self.log(f"Error analyzing {pdf_path.name}: {e}", "WARN")
        return spans
    
    def run_single_test(self, test: TestCase) -> TestResult:
        """Run a single test case and return the result."""
        self.log(f"\n{'='*60}")
        self.log(f"Test: {test.name}")
        self.log(f"  Target: '{test.target_text}'")
        self.log(f"  Replace: '{test.replacement_text}'")
        self.log(f"  Page: {test.page_number}")
        
        result = TestResult(
            test_name=test.name,
            passed=False,
            target_found_before=False,
            replacement_found_after=False,
            target_found_after=False,
            api_success=False,
            api_message="",
        )
        
        # Create temp copy of PDF
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                shutil.copy(test.pdf_path, tmp.name)
                work_path = tmp.name
            
            out_path = work_path.replace('.pdf', '_out.pdf')
            
            # Check if target exists before edit
            doc = fitz.open(work_path)
            page = doc[test.page_number - 1]
            text_before = page.get_text()
            result.target_found_before = test.target_text in text_before
            # Count occurrences for deletion test
            target_count_before = text_before.count(test.target_text)
            doc.close()
            
            if not result.target_found_before:
                self.log(f"  Target text not found in PDF before edit!", "WARN")
            
            # Run the replacement
            api_result = core.replace_text_in_pdf(
                input_path=work_path,
                output_path=out_path,
                target_text=test.target_text,
                replacement_text=test.replacement_text,
                page_number=test.page_number,
                manual_overrides=test.overrides,
            )
            
            result.api_success = api_result.get("success", False)
            result.api_message = api_result.get("message", "")
            result.debug_log = api_result.get("debug_log", [])
            
            self.log(f"  API Success: {result.api_success}")
            self.log(f"  API Message: {result.api_message}")
            
            # Check output file
            if os.path.exists(out_path):
                doc = fitz.open(out_path)
                page = doc[test.page_number - 1]
                # Use wide clip to catch text that may extend past page bounds
                text_after = page.get_text(clip=fitz.Rect(-100, -100, 2000, 2000))
                
                result.replacement_found_after = test.replacement_text in text_after
                result.target_found_after = test.target_text in text_after
                target_count_after = text_after.count(test.target_text)
                doc.close()
                
                self.log(f"  Replacement found after: {result.replacement_found_after}")
                self.log(f"  Original still exists: {result.target_found_after}")
                
                # Determine pass/fail
                if test.replacement_text:
                    # Normal replacement: should find replacement, should NOT find original
                    # (unless there were multiple instances)
                    result.passed = result.replacement_found_after
                else:
                    # Delete operation: count should decrease by at least 1
                    # (handles cases where target appears multiple times in PDF)
                    self.log(f"  Target count: {target_count_before} -> {target_count_after}")
                    result.passed = target_count_after < target_count_before
                    
                os.unlink(out_path)
            else:
                result.error = "Output file was not created"
                self.log(f"  ERROR: Output file not created!", "FAIL")
            
            os.unlink(work_path)
            
        except Exception as e:
            result.error = str(e)
            self.log(f"  EXCEPTION: {e}", "FAIL")
        
        if result.passed:
            self.log(f"  Result: PASSED", "OK")
        else:
            self.log(f"  Result: FAILED", "FAIL")
            
        return result
    
    def generate_test_cases(self) -> List[TestCase]:
        """Generate test cases from available PDFs."""
        test_cases = []
        
        # Known test files
        billing_pdf = SAMPLE_FILES / "billing-statement-invoice-orig2.pdf"
        insurance_pdf = SAMPLE_FILES / " 2.pdf"  # Note the space
        
        # Test Case 1: Billing statement - Berkley One (the failing case)
        if billing_pdf.exists():
            test_cases.append(TestCase(
                name="Billing_BerkleyOne_to_BerkleyTwo",
                pdf_path=str(billing_pdf),
                page_number=1,
                target_text="Berkley One",
                replacement_text="Berkley Two",
            ))
            
            # With empty overrides dict (simulates app behavior)
            test_cases.append(TestCase(
                name="Billing_BerkleyOne_with_overrides",
                pdf_path=str(billing_pdf),
                page_number=1,
                target_text="Berkley One",
                replacement_text="Berkley Two",
                overrides={
                    'manual_size_delta': 0.0,
                    'manual_x_offset': 0.0,
                    'manual_y_offset': 0.0,
                    'manual_tracking_delta': 0.0,
                },
            ))
            
            # Test deletion (empty replacement)
            test_cases.append(TestCase(
                name="Billing_Delete",
                pdf_path=str(billing_pdf),
                page_number=1,
                target_text="Berkley One",
                replacement_text="",
            ))
        
        # Test Case 2: Insurance PDF with obfuscated fonts
        if insurance_pdf.exists():
            test_cases.append(TestCase(
                name="Insurance_Cancellation",
                pdf_path=str(insurance_pdf),
                page_number=6,
                target_text="A. CANCELLATION",
                replacement_text="A. NEW CANCELLATION",
            ))
        
        # Add more dynamic test cases from other PDFs
        for pdf_path in self.find_test_pdfs()[:5]:  # First 5 PDFs
            if pdf_path.name in ['billing-statement-invoice-orig2.pdf', ' 2.pdf']:
                continue  # Already covered
                
            spans = self.analyze_pdf(pdf_path)
            if spans:
                # Pick the first suitable span
                span = spans[0]
                test_cases.append(TestCase(
                    name=f"Auto_{pdf_path.stem[:20]}_{span['text'][:10]}",
                    pdf_path=str(pdf_path),
                    page_number=span['page'],
                    target_text=span['text'],
                    replacement_text=f"[REPLACED] {span['text'][:10]}",
                ))
        
        return test_cases
    
    def run_all_tests(self) -> dict:
        """Run all test cases and return summary."""
        test_cases = self.generate_test_cases()
        self.log(f"\nGenerated {len(test_cases)} test cases")
        
        for tc in test_cases:
            result = self.run_single_test(tc)
            self.results.append(result)
        
        # Summary
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        summary = {
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "results": [
                {
                    "name": r.test_name,
                    "passed": r.passed,
                    "api_success": r.api_success,
                    "api_message": r.api_message,
                    "target_found_before": r.target_found_before,
                    "replacement_found_after": r.replacement_found_after,
                    "target_found_after": r.target_found_after,
                    "error": r.error,
                }
                for r in self.results
            ],
        }
        
        self.log(f"\n{'='*60}")
        self.log(f"SUMMARY: {passed}/{len(self.results)} tests passed")
        
        if failed > 0:
            self.log(f"\nFailed tests:", "FAIL")
            for r in self.results:
                if not r.passed:
                    self.log(f"  - {r.test_name}: {r.error or r.api_message}", "FAIL")
        
        return summary
    
    def diagnose_issue(self) -> str:
        """Analyze results to diagnose the issue."""
        if not self.results:
            return "No tests run yet."
        
        failed = [r for r in self.results if not r.passed]
        if not failed:
            return "All tests passed - Python API is working correctly. Issue is likely in Swift/UI layer."
        
        # Analyze failure patterns
        api_failures = [r for r in failed if not r.api_success]
        replacement_missing = [r for r in failed if r.api_success and not r.replacement_found_after]
        
        diagnosis = []
        
        if api_failures:
            diagnosis.append("API returned failure for some tests:")
            for r in api_failures:
                diagnosis.append(f"  - {r.test_name}: {r.api_message}")
        
        if replacement_missing:
            diagnosis.append("API succeeded but replacement text not found:")
            for r in replacement_missing:
                diagnosis.append(f"  - {r.test_name}")
            diagnosis.append("  → This suggests text insertion is failing after redaction")
            
        if not diagnosis:
            diagnosis.append("Unknown failure pattern - check individual test results")
        
        return "\n".join(diagnosis)


def main():
    """Main entry point."""
    print("=" * 60)
    print("  TEXT EDIT TEST HARNESS")
    print("  Automated diagnosis of text replacement issues")
    print("=" * 60)
    
    harness = TextEditTestHarness(verbose=True)
    summary = harness.run_all_tests()
    
    print("\n" + "=" * 60)
    print("DIAGNOSIS:")
    print("=" * 60)
    print(harness.diagnose_issue())
    
    # Save results to JSON
    results_path = SCRIPT_DIR / "text_edit_results.json"
    with open(results_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to: {results_path}")
    
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
