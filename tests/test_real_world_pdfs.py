#!/usr/bin/env python3
"""
Real-World PDF Testing Harness
Automatically tests editing on all PDFs in sample-files directory
Picks 10 text blocks per PDF and attempts edits, reporting success/failure patterns
"""

import sys
import os
import time
import fitz
import json
import random
from pathlib import Path

# Add python_site to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
python_site = os.path.join(_PROJECT_ROOT, 'Sources', 'Marcedit', 'python_site')
sys.path.insert(0, python_site)

from editor_pkg import core

# Sample files directory
SAMPLE_DIR = "ignored-resources/sample-files-marcedit"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ignored-resources", "real_world_test_results")


class EditResult:
    """Stores test result for a single edit."""
    def __init__(self, pdf_name, page_num, original_text, replacement_text):
        self.pdf_name = pdf_name
        self.page_num = page_num
        self.original_text = original_text[:50]  # Truncate for readability
        self.replacement_text = replacement_text[:50]
        self.success = False
        self.error_type = None
        self.error_message = None
        self.duration_ms = 0
        self.collision_info = None

    def to_dict(self):
        return {
            'pdf_name': self.pdf_name,
            'page_num': self.page_num,
            'original_text': self.original_text,
            'replacement_text': self.replacement_text,
            'success': self.success,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'duration_ms': self.duration_ms,
            'collision_info': self.collision_info
        }


def extract_text_blocks(pdf_path, max_blocks=10):
    """
    Extract up to max_blocks text blocks from PDF.

    Returns:
        list of dicts with keys: page_num, text, bbox
    """
    blocks = []

    try:
        doc = fitz.open(pdf_path)

        for page_num in range(len(doc)):
            page = doc[page_num]
            text_dict = page.get_text("dict")

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # Not text block
                    continue

                # Extract text from lines
                block_text = ""
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        block_text += span.get("text", "")
                    block_text += " "

                block_text = block_text.strip()

                # Filter criteria
                if len(block_text) < 10:  # Too short
                    continue
                if len(block_text) > 200:  # Too long
                    continue
                if not any(c.isalpha() for c in block_text):  # No letters
                    continue
                # Skip blocks with Unicode noncharacters or replacement chars —
                # these indicate undecodable PDF encoding and will always fail.
                if any(ord(c) >= 0xFFFD for c in block_text):
                    continue
                # Skip multi-line blocks: concatenated text may not match the PDF's
                # internal representation (hyphenation, line-break spacing, etc.).
                if len(block.get("lines", [])) > 1:
                    continue

                blocks.append({
                    'page_num': page_num + 1,  # 1-indexed
                    'text': block_text,
                    'bbox': block.get("bbox")
                })

                if len(blocks) >= max_blocks:
                    doc.close()
                    return blocks

        doc.close()

    except Exception as e:
        print(f"    Error extracting blocks: {e}")
        return []

    return blocks


def generate_replacement_text(original_text):
    """
    Generate a realistic replacement text based on the original.

    Strategy:
    - Keep similar length
    - Make obvious change (add [EDITED] marker)
    - Preserve some structure
    """
    # Simple strategy: add [EDITED] prefix
    replacement = f"[EDITED] {original_text}"

    # If too long, truncate and add marker
    if len(replacement) > 150:
        replacement = "[EDITED] " + original_text[:120] + "..."

    return replacement


def run_single_edit(pdf_path, page_num, original_text, replacement_text):
    """
    Test a single edit operation.

    Returns:
        TestResult object
    """
    pdf_name = os.path.basename(pdf_path)
    result = EditResult(pdf_name, page_num, original_text, replacement_text)

    # Create temp output path
    import tempfile
    fd, output_path = tempfile.mkstemp(suffix='.pdf', prefix='test_')
    os.close(fd)

    try:
        start_time = time.time()

        # Attempt the edit
        edit_result = core.replace_text_in_pdf(
            input_path=pdf_path,
            output_path=output_path,
            target_text=original_text,
            replacement_text=replacement_text,
            page_number=page_num
        )

        result.duration_ms = (time.time() - start_time) * 1000
        result.success = edit_result.get('success', False)

        if not result.success:
            result.error_message = edit_result.get('message', 'Unknown error')

            # Categorize error types
            msg = result.error_message.lower()
            if 'collision' in msg:
                result.error_type = 'collision'
                # Extract collision details if available
                if 'pixels' in msg:
                    result.collision_info = result.error_message
            elif 'not found' in msg or 'no match' in msg:
                result.error_type = 'text_not_found'
            elif 'font' in msg:
                result.error_type = 'font_issue'
            elif 'dimension' in msg:
                result.error_type = 'dimension_mismatch'
            else:
                result.error_type = 'other'

    except Exception as e:
        result.error_type = 'exception'
        result.error_message = str(e)
        result.duration_ms = (time.time() - start_time) * 1000

    finally:
        # Cleanup
        if os.path.exists(output_path):
            os.unlink(output_path)

    return result


def run_pdf_tests(pdf_path, max_edits=10):
    """
    Test editing on a single PDF.

    Returns:
        list of TestResult objects
    """
    pdf_name = os.path.basename(pdf_path)
    print(f"\n{'='*70}")
    print(f"Testing: {pdf_name}")
    print(f"{'='*70}")

    # Extract text blocks
    print(f"  Extracting text blocks...")
    blocks = extract_text_blocks(pdf_path, max_blocks=max_edits)

    if not blocks:
        print(f"  ⚠ No suitable text blocks found")
        return []

    print(f"  Found {len(blocks)} text blocks to test")

    # Test each block
    results = []

    for i, block in enumerate(blocks):
        original_text = block['text']
        replacement_text = generate_replacement_text(original_text)
        page_num = block['page_num']

        print(f"\n  [{i+1}/{len(blocks)}] Page {page_num}: '{original_text[:40]}...'")

        result = run_single_edit(pdf_path, page_num, original_text, replacement_text)
        results.append(result)

        if result.success:
            print(f"        ✓ Success ({result.duration_ms:.0f}ms)")
        else:
            print(f"        ✗ Failed: {result.error_type}")
            print(f"          {result.error_message[:80]}")

    return results


def run_all_tests():
    """
    Run tests on all PDFs in sample directory.

    Returns:
        dict with comprehensive results
    """
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Find all PDFs
    pdf_files = sorted(Path(SAMPLE_DIR).glob("*.pdf"))
    pdf_files = [p for p in pdf_files if p.name != '.gitkeep']

    print(f"{'='*70}")
    print(f"REAL-WORLD PDF TESTING HARNESS")
    print(f"{'='*70}")
    print(f"\nFound {len(pdf_files)} PDFs in {SAMPLE_DIR}")
    print(f"Testing up to 10 edits per PDF")
    print(f"Results will be saved to {OUTPUT_DIR}\n")

    all_results = []
    pdf_summaries = []

    overall_start = time.time()

    # Test each PDF
    for pdf_path in pdf_files:
        try:
            results = run_pdf_tests(str(pdf_path), max_edits=10)
            all_results.extend(results)

            # Summary for this PDF
            total = len(results)
            successes = sum(1 for r in results if r.success)
            failures = total - successes

            # Categorize failures
            failure_types = {}
            for r in results:
                if not r.success and r.error_type:
                    failure_types[r.error_type] = failure_types.get(r.error_type, 0) + 1

            avg_duration = sum(r.duration_ms for r in results) / total if total > 0 else 0

            summary = {
                'pdf_name': os.path.basename(pdf_path),
                'total_tests': total,
                'successes': successes,
                'failures': failures,
                'success_rate': (successes / total * 100) if total > 0 else 0,
                'avg_duration_ms': avg_duration,
                'failure_types': failure_types
            }

            pdf_summaries.append(summary)

            print(f"\n  Summary: {successes}/{total} successful ({summary['success_rate']:.1f}%)")
            if failure_types:
                print(f"  Failures by type:")
                for error_type, count in sorted(failure_types.items()):
                    print(f"    - {error_type}: {count}")

        except Exception as e:
            print(f"\n  ✗ Exception testing PDF: {e}")
            import traceback
            traceback.print_exc()

    overall_duration = time.time() - overall_start

    # Generate comprehensive report
    total_tests = len(all_results)
    total_successes = sum(1 for r in all_results if r.success)
    total_failures = total_tests - total_successes

    # Aggregate failure types
    all_failure_types = {}
    for r in all_results:
        if not r.success and r.error_type:
            all_failure_types[r.error_type] = all_failure_types.get(r.error_type, 0) + 1

    report = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_pdfs': len(pdf_files),
        'total_tests': total_tests,
        'total_successes': total_successes,
        'total_failures': total_failures,
        'overall_success_rate': (total_successes / total_tests * 100) if total_tests > 0 else 0,
        'overall_duration_seconds': overall_duration,
        'failure_types': all_failure_types,
        'pdf_summaries': pdf_summaries,
        'detailed_results': [r.to_dict() for r in all_results]
    }

    # Save detailed JSON report
    report_path = os.path.join(OUTPUT_DIR, 'test_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Print final summary
    print(f"\n\n{'='*70}")
    print(f"FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"\nTested {len(pdf_files)} PDFs with {total_tests} total edits")
    print(f"\n📊 Overall Results:")
    print(f"  ✓ Successes: {total_successes}/{total_tests} ({report['overall_success_rate']:.1f}%)")
    print(f"  ✗ Failures:  {total_failures}/{total_tests}")
    print(f"\n⏱  Duration: {overall_duration:.1f}s")

    if all_failure_types:
        print(f"\n🔍 Failure Analysis:")
        for error_type, count in sorted(all_failure_types.items(), key=lambda x: -x[1]):
            percentage = (count / total_failures * 100) if total_failures > 0 else 0
            print(f"  - {error_type}: {count} ({percentage:.1f}% of failures)")

    print(f"\n📄 Per-PDF Success Rates:")
    for summary in sorted(pdf_summaries, key=lambda x: x['success_rate']):
        print(f"  {summary['success_rate']:5.1f}% - {summary['pdf_name'][:50]} ({summary['successes']}/{summary['total_tests']})")

    print(f"\n💾 Detailed report saved to: {report_path}")

    # Identify patterns
    print(f"\n\n{'='*70}")
    print(f"ACTIONABLE INSIGHTS")
    print(f"{'='*70}")

    if all_failure_types:
        # Top issue
        top_issue = max(all_failure_types.items(), key=lambda x: x[1])
        print(f"\n🎯 Top Issue: {top_issue[0]} ({top_issue[1]} occurrences)")

        if top_issue[0] == 'collision':
            print(f"   → Action: Review collision detection thresholds")
            print(f"   → Investigate: Are collisions false positives or real?")

            # Find collision examples
            collision_examples = [r for r in all_results if r.error_type == 'collision'][:3]
            print(f"\n   Example collision errors:")
            for ex in collision_examples:
                print(f"     - {ex.pdf_name}, page {ex.page_num}")
                print(f"       {ex.collision_info[:100] if ex.collision_info else ex.error_message[:100]}")

        elif top_issue[0] == 'text_not_found':
            print(f"   → Action: Review text extraction/matching logic")
            print(f"   → Investigate: Unicode normalization, whitespace handling")

        elif top_issue[0] == 'font_issue':
            print(f"   → Action: Review font identification and fallback")
            print(f"   → Investigate: Embedded font handling")

    # PDFs with 100% failure
    zero_success = [s for s in pdf_summaries if s['success_rate'] == 0]
    if zero_success:
        print(f"\n⚠️  PDFs with 0% success rate ({len(zero_success)} PDFs):")
        for s in zero_success:
            print(f"   - {s['pdf_name']}")
            print(f"     Failure types: {s['failure_types']}")

    # PDFs with 100% success
    perfect = [s for s in pdf_summaries if s['success_rate'] == 100]
    if perfect:
        print(f"\n✅ PDFs with 100% success rate ({len(perfect)} PDFs):")
        for s in perfect:
            print(f"   - {s['pdf_name']}")

    print(f"\n{'='*70}\n")

    return report


if __name__ == "__main__":
    report = run_all_tests()

    # Exit code based on success rate
    success_rate = report['overall_success_rate']

    if success_rate >= 90:
        print("🎉 Excellent! Success rate >= 90%")
        sys.exit(0)
    elif success_rate >= 70:
        print("⚠️  Good, but room for improvement (70-90%)")
        sys.exit(0)
    else:
        print("❌ Needs attention - success rate < 70%")
        sys.exit(1)
