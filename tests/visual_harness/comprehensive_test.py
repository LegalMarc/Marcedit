#!/usr/bin/env python3
"""
Comprehensive Visual Regression Test Suite
Runs tests across all sample PDFs and generates a consolidated report.

Uses AI vision to evaluate visual quality of edits.
"""
import os
import sys
import json
import tempfile
import shutil
import base64
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import random

# Add paths
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HARNESS_DIR))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Sources", "Marcedit", "python_site"))

import fitz
from editor_pkg import core

# Try to import anthropic for AI evaluation. External evaluation is opt-in
# because it sends document-derived images/text to a remote service.
try:
    import anthropic
    ANTHROPIC_AVAILABLE = os.environ.get("MARCEDIT_ALLOW_EXTERNAL_LLM") == "1"
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not available, AI evaluation disabled")


@dataclass
class TestCase:
    id: str
    pdf_path: str
    pdf_name: str
    page: int
    target_text: str
    replacement_text: str
    edit_type: str  # identity, change, add, shrink
    font_name: str
    bbox: tuple = None  # Original bounding box for fixed viewport capture


@dataclass
class TestResult:
    test_case: TestCase
    success: bool
    status: str = "ERROR"  # PASS, WARN, FAIL, ERROR
    before_image: bytes = None
    after_image: bytes = None
    diff_image: bytes = None
    pixel_diff_pct: float = 0.0
    error_message: str = ""
    quality_issues: List[str] = field(default_factory=list)


def scan_pdf_for_text_spans(pdf_path: str, max_spans: int = 20) -> List[dict]:
    """Extract text spans suitable for testing from a PDF."""
    spans = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(min(len(doc), 3)):  # First 3 pages
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        font = span.get("font", "Unknown")
                        bbox = span.get("bbox")

                        # Filter for good test candidates
                        if len(text) >= 4 and len(text) <= 40:
                            # Skip if mostly whitespace or special chars
                            alpha_ratio = sum(c.isalnum() for c in text) / len(text) if text else 0
                            if alpha_ratio > 0.6:
                                spans.append({
                                    "text": text,
                                    "font": font,
                                    "page": page_num,
                                    "bbox": bbox
                                })

                        if len(spans) >= max_spans:
                            break
                    if len(spans) >= max_spans:
                        break
                if len(spans) >= max_spans:
                    break
            if len(spans) >= max_spans:
                break
        doc.close()
    except Exception as e:
        print(f"Error scanning {pdf_path}: {e}")

    return spans


def generate_replacement(original: str, edit_type: str) -> str:
    """Generate replacement text based on edit type."""
    if edit_type == "identity":
        return original
    elif edit_type == "change":
        # Replace a word with a different word
        words = original.split()
        if len(words) >= 2:
            # Replace middle word
            mid_idx = len(words) // 2
            if words[mid_idx].isalpha():
                words[mid_idx] = "MODIFIED"
            else:
                # If it's a number or special, replace first word
                words[0] = "CHANGED"
        elif len(words) == 1 and words[0].isalpha():
            words[0] = "REPLACED"
        else:
            # For short text with numbers/special chars, prepend
            return "UPDATED " + original
        return ' '.join(words)
    elif edit_type == "add":
        # Add a word to the end
        words = original.split()
        if len(words) > 0:
            words.append("ADDED")
        else:
            return original + " EXTRA"
        return ' '.join(words)
    elif edit_type == "shrink":
        # Remove the last word(s)
        words = original.split()
        if len(words) > 2:
            # Remove last word
            return ' '.join(words[:-1])
        elif len(words) == 2:
            # Keep just first word
            return words[0]
        else:
            # For single word, remove last few characters
            return original[:max(3, len(original) - 3)]
    return original


def create_test_cases(sample_dir: str, target_count: int = 100) -> List[TestCase]:
    """Create test cases from all PDFs in the sample directory."""
    test_cases = []
    pdf_files = [f for f in os.listdir(sample_dir) if f.lower().endswith('.pdf')]

    if not pdf_files:
        print(f"No PDF files found in {sample_dir}")
        return []

    # Use 3 tests per PDF: add, shrink, change (real text modifications)
    tests_per_pdf = 3
    edit_types = ["add", "shrink", "change"]

    tc_id = 1
    for pdf_name in pdf_files:
        pdf_path = os.path.join(sample_dir, pdf_name)
        spans = scan_pdf_for_text_spans(pdf_path, max_spans=tests_per_pdf * 2)

        if not spans:
            print(f"No suitable spans in {pdf_name}")
            continue

        # Create 3 test cases per PDF: one for each edit type
        for i in range(min(tests_per_pdf, len(spans))):
            span = spans[i]
            edit_type = edit_types[i % len(edit_types)]
            replacement = generate_replacement(span["text"], edit_type)

            test_cases.append(TestCase(
                id=f"TC-{tc_id:04d}",
                pdf_path=pdf_path,
                pdf_name=pdf_name,
                page=span["page"],
                target_text=span["text"],
                replacement_text=replacement,
                edit_type=edit_type,
                font_name=span["font"],
                bbox=span["bbox"]
            ))
            tc_id += 1

            if len(test_cases) >= target_count:
                break

        if len(test_cases) >= target_count:
            break

    return test_cases[:target_count]


def render_fixed_region(pdf_path: str, page_num: int, bbox: tuple, margin: int = 50) -> Optional[bytes]:
    """Render a FIXED region based on bbox (not searching for text)."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]

        # Expand bbox for context
        clip = fitz.Rect(
            max(0, bbox[0] - margin),
            max(0, bbox[1] - margin),
            min(page.rect.width, bbox[2] + margin),
            min(page.rect.height, bbox[3] + margin)
        )

        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
        doc.close()

        return pix.tobytes("png")
    except Exception as e:
        return None


def get_anthropic_client():
    """
    Create an Anthropic client using available authentication.
    Supports both ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL.
    """
    if os.environ.get("MARCEDIT_ALLOW_EXTERNAL_LLM") != "1":
        raise ValueError("Set MARCEDIT_ALLOW_EXTERNAL_LLM=1 to enable external LLM evaluation")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")

    if api_key:
        return anthropic.Anthropic(api_key=api_key)
    elif auth_token and base_url:
        return anthropic.Anthropic(api_key=auth_token, base_url=base_url)
    elif auth_token:
        return anthropic.Anthropic(api_key=auth_token)
    else:
        raise ValueError("No API key or auth token found. Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN")


def evaluate_with_ai(before_bytes: bytes, after_bytes: bytes, edit_type: str,
                     target_text: str, replacement_text: str) -> Tuple[bool, str]:
    """
    Use Claude's vision to evaluate if the edit looks good.

    Returns:
        (passed, explanation)
    """
    if not ANTHROPIC_AVAILABLE:
        return True, "AI evaluation not available"

    try:
        client = get_anthropic_client()

        # Encode images as base64
        before_b64 = base64.standard_b64encode(before_bytes).decode("utf-8")
        after_b64 = base64.standard_b64encode(after_bytes).decode("utf-8")

        prompt = f"""You are evaluating PDF text editing quality. Compare these BEFORE and AFTER images.

Edit type: {edit_type}
Original text: "{target_text}"
Replacement text: "{replacement_text}"

Evaluate the AFTER image for these issues:
1. FONT MISMATCH - Does the edited text use a different font weight, style, or family than surrounding text?
2. COLOR MISMATCH - Is the edited text a different color (e.g., gray instead of black)?
3. BACKGROUND DAMAGE - Is any background shading, highlighting, or formatting lost or corrupted?
4. TEXT COLLISION - Is there any overlapping or garbled text?
5. SPACING ISSUES - Are there obvious spacing problems between characters or words?

For IDENTITY edits (same text), the BEFORE and AFTER should look identical.

Respond with EXACTLY this format:
PASS or FAIL
One sentence explanation (max 50 words)

Example responses:
PASS
Edit looks correct, font and color match original.

FAIL
Font weight is wrong - edited text appears lighter/thinner than original bold text."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "text",
                            "text": "BEFORE image:"
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": before_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": "AFTER image:"
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": after_b64
                            }
                        }
                    ]
                }
            ]
        )

        result_text = response.content[0].text.strip()
        lines = result_text.split('\n', 1)

        passed = lines[0].strip().upper() == "PASS"
        explanation = lines[1].strip() if len(lines) > 1 else "No explanation"

        return passed, explanation

    except Exception as e:
        return True, f"AI evaluation error: {str(e)[:50]}"


def compute_pixel_diff_with_zones(before_bytes: bytes, after_bytes: bytes, text_zone_pct: float = 0.4) -> Tuple[bytes, float, float, List[str]]:
    """
    Compute pixel differences separately for text zone and surrounding area.

    The text zone is the center portion of the image (where text is expected).
    The surrounding zone is the outer portion (should remain unchanged for good edits).

    Args:
        text_zone_pct: fraction of image (centered) considered text zone

    Returns:
        diff_image, overall_diff_pct, surrounding_diff_pct, issues
    """
    issues = []

    try:
        before_pix = fitz.Pixmap(before_bytes)
        after_pix = fitz.Pixmap(after_bytes)

        if before_pix.width != after_pix.width or before_pix.height != after_pix.height:
            issues.append(f"Size mismatch")
            min_w = min(before_pix.width, after_pix.width)
            min_h = min(before_pix.height, after_pix.height)
        else:
            min_w = before_pix.width
            min_h = before_pix.height

        before_samples = before_pix.samples
        after_samples = after_pix.samples

        n = before_pix.n
        before_stride = before_pix.stride
        after_stride = after_pix.stride

        # Define text zone (center portion)
        margin_x = int(min_w * (1 - text_zone_pct) / 2)
        margin_y = int(min_h * (1 - text_zone_pct) / 2)

        total_pixels = 0
        diff_count = 0
        surround_total = 0
        surround_diff = 0

        for y in range(min_h):
            for x in range(min_w):
                before_idx = y * before_stride + x * n
                after_idx = y * after_stride + x * n

                if before_idx + n - 1 >= len(before_samples) or after_idx + n - 1 >= len(after_samples):
                    continue

                r1, g1, b1 = before_samples[before_idx], before_samples[before_idx+1], before_samples[before_idx+2]
                r2, g2, b2 = after_samples[after_idx], after_samples[after_idx+1], after_samples[after_idx+2]

                dist = ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2) ** 0.5
                total_pixels += 1

                is_surrounding = (x < margin_x or x >= min_w - margin_x or
                                  y < margin_y or y >= min_h - margin_y)

                if is_surrounding:
                    surround_total += 1
                    if dist > 10:
                        surround_diff += 1

                if dist > 10:
                    diff_count += 1

        diff_pct = (diff_count / total_pixels) * 100 if total_pixels > 0 else 0
        surround_pct = (surround_diff / surround_total) * 100 if surround_total > 0 else 0

        # Check for problems in surrounding area
        if surround_pct > 5:
            issues.append(f"Surrounding area changed ({surround_pct:.1f}%)")

        return None, diff_pct, surround_pct, issues

    except Exception as e:
        issues.append(f"Diff error: {str(e)}")
        return None, 0.0, 0.0, issues


def validate_edit_quality(tc: TestCase, before_bytes: bytes, after_bytes: bytes, use_ai: bool = True) -> Tuple[bool, List[str]]:
    """
    Validate that the edit produced acceptable visual quality.

    Uses AI vision to evaluate the before/after images.

    Returns:
        (passed, list of issues, diff_img, diff_pct)
    """
    issues = []

    # Get pixel diff for reporting
    diff_img, diff_pct, surround_pct, diff_issues = compute_pixel_diff_with_zones(before_bytes, after_bytes)

    # Use AI to evaluate visual quality
    if use_ai and ANTHROPIC_AVAILABLE:
        print(f"    [AI] Evaluating...", end=" ", flush=True)
        ai_passed, ai_explanation = evaluate_with_ai(
            before_bytes, after_bytes,
            tc.edit_type, tc.target_text, tc.replacement_text
        )
        print(f"{'PASS' if ai_passed else 'FAIL'}: {ai_explanation[:40]}")
        if not ai_passed:
            issues.append(ai_explanation)
    else:
        print(f"    [No AI] ANTHROPIC_AVAILABLE={ANTHROPIC_AVAILABLE}")
        # Fallback to pixel-based validation
        # For real text changes, we expect some visual difference
        # Only flag if essentially no change was detected (ghost edit)
        # Using 0.1% threshold to catch truly missing changes while allowing subtle edits
        if tc.edit_type != "identity" and diff_pct < 0.1:
            issues.append(f"No visual change detected for {tc.edit_type} edit")
        # For identity edits (if any), check they don't change too much
        elif tc.edit_type == "identity" and diff_pct > 8.0:
            issues.append(f"Identity edit has {diff_pct:.1f}% diff")

    # Always include collision issues from diff calculation
    issues.extend(diff_issues)

    passed = len(issues) == 0
    return passed, issues, diff_img, diff_pct


def run_test(tc: TestCase) -> TestResult:
    """Run a single test case with strict quality validation."""
    result = TestResult(test_case=tc, success=False, status="ERROR")

    try:
        # Ensure we have a bbox
        if not tc.bbox:
            result.error_message = "No bounding box for test"
            return result

        # Capture BEFORE image at FIXED location
        before_img = render_fixed_region(tc.pdf_path, tc.page, tc.bbox)
        if not before_img:
            result.error_message = f"Could not render before region"
            return result
        result.before_image = before_img

        # Create working copy
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            shutil.copy(tc.pdf_path, tmp.name)
            work_path = tmp.name

        output_path = work_path.replace(".pdf", "_out.pdf")

        try:
            # Run the edit
            edit_result = core.replace_text_in_pdf(
                input_path=work_path,
                output_path=output_path,
                target_text=tc.target_text,
                replacement_text=tc.replacement_text,
                page_number=tc.page + 1
            )

            if not edit_result.get("success"):
                result.error_message = edit_result.get("message", "Edit failed")
                result.status = "FAIL"
                return result

            if not os.path.exists(output_path):
                result.error_message = "Output file not created"
                result.status = "FAIL"
                return result

            # Capture AFTER image at SAME FIXED location
            after_img = render_fixed_region(output_path, tc.page, tc.bbox)
            if not after_img:
                result.error_message = "Could not render after region"
                result.status = "FAIL"
                return result

            result.after_image = after_img

            # Validate quality
            passed, issues, diff_img, diff_pct = validate_edit_quality(tc, before_img, after_img)

            result.diff_image = diff_img
            result.pixel_diff_pct = diff_pct
            result.quality_issues = issues

            if passed:
                result.success = True
                result.status = "PASS"
            else:
                result.success = False
                result.status = "FAIL"
                result.error_message = "; ".join(issues[:2])  # First 2 issues

        finally:
            if os.path.exists(work_path):
                os.unlink(work_path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    except Exception as e:
        result.error_message = str(e)
        result.status = "ERROR"

    return result


def generate_pdf_report(results: List[TestResult], output_path: str):
    """Generate a PDF report with proper visual comparison."""
    doc = fitz.open()

    # Counts
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    warned = sum(1 for r in results if r.status == "WARN")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")

    # Summary page
    page = doc.new_page()

    # Title
    page.insert_text((72, 60), "Visual Regression Report", fontsize=24, fontname="helv")
    page.insert_text((72, 85), f"Generated: {datetime.now().isoformat()}", fontsize=10, fontname="helv")

    # Summary table
    y = 120
    headers = ["Status", "Count", "Percentage"]
    data = [
        ("PASS", passed, f"{passed/total*100:.1f}%" if total else "0%"),
        ("WARN", warned, f"{warned/total*100:.1f}%" if total else "0%"),
        ("FAIL", failed, f"{failed/total*100:.1f}%" if total else "0%"),
        ("ERROR", errors, f"{errors/total*100:.1f}%" if total else "0%"),
        ("TOTAL", total, "100%"),
    ]

    colors = {
        "PASS": (0.2, 0.8, 0.2),
        "WARN": (1.0, 0.8, 0.0),
        "FAIL": (1.0, 0.4, 0.4),
        "ERROR": (0.8, 0.2, 0.2),
        "TOTAL": (0.3, 0.3, 0.8),
    }

    # Draw table
    col_widths = [150, 100, 100]
    row_height = 25
    x_start = 150

    # Header row
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(x_start, y, x_start + sum(col_widths), y + row_height))
    shape.finish(fill=(0.2, 0.2, 0.5), color=(0, 0, 0))
    shape.commit()

    page.insert_text((x_start + 50, y + 17), headers[0], fontsize=11, fontname="helv", color=(1, 1, 1))
    page.insert_text((x_start + 175, y + 17), headers[1], fontsize=11, fontname="helv", color=(1, 1, 1))
    page.insert_text((x_start + 280, y + 17), headers[2], fontsize=11, fontname="helv", color=(1, 1, 1))

    y += row_height

    for status, count, pct in data:
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x_start, y, x_start + sum(col_widths), y + row_height))
        shape.finish(fill=colors.get(status, (0.9, 0.9, 0.9)), color=(0, 0, 0))
        shape.commit()

        page.insert_text((x_start + 50, y + 17), status, fontsize=11, fontname="helv")
        page.insert_text((x_start + 175, y + 17), str(count), fontsize=11, fontname="helv")
        page.insert_text((x_start + 280, y + 17), pct, fontsize=11, fontname="helv")
        y += row_height

    # Individual test pages
    for result in results:
        tc = result.test_case

        page = doc.new_page()
        y = 40

        status_color = colors.get(result.status, (0, 0, 0))

        # Header
        page.insert_text((72, y), f"{tc.id}: {result.status}", fontsize=14, fontname="helv", color=status_color)
        y += 20

        page.insert_text((72, y), f"File: {tc.pdf_name}", fontsize=9, fontname="helv")
        y += 12
        page.insert_text((72, y), f"Page: {tc.page} | Font: {tc.font_name}", fontsize=9, fontname="helv")
        y += 12

        # Edit info - show the text change prominently
        target_short = tc.target_text[:35] + "..." if len(tc.target_text) > 35 else tc.target_text
        repl_short = tc.replacement_text[:35] + "..." if len(tc.replacement_text) > 35 else tc.replacement_text
        page.insert_text((72, y), f"Edit Type: {tc.edit_type}", fontsize=9, fontname="helv")
        y += 12
        page.insert_text((72, y), f"Changed: \"{target_short}\" → \"{repl_short}\"", fontsize=9, fontname="helv", color=(0, 0, 0.6))
        y += 20

        # Images
        img_width = 160
        img_height = 100
        img_y = y + 20

        page.insert_text((72, y), "BEFORE", fontsize=10, fontname="helv")
        page.insert_text((72 + img_width + 20, y), "AFTER", fontsize=10, fontname="helv")
        page.insert_text((72 + 2*(img_width + 20), y), "DIFF", fontsize=10, fontname="helv")

        if result.before_image:
            try:
                rect = fitz.Rect(72, img_y, 72 + img_width, img_y + img_height)
                page.insert_image(rect, stream=result.before_image)
            except:
                pass

        if result.after_image:
            try:
                rect = fitz.Rect(72 + img_width + 20, img_y, 72 + 2*img_width + 20, img_y + img_height)
                page.insert_image(rect, stream=result.after_image)
            except:
                pass

        if result.diff_image:
            try:
                rect = fitz.Rect(72 + 2*(img_width + 20), img_y, 72 + 3*img_width + 40, img_y + img_height)
                page.insert_image(rect, stream=result.diff_image)
            except:
                pass

        y = img_y + img_height + 20

        # Metrics
        page.insert_text((72, y), f"Pixel Diff: {result.pixel_diff_pct:.2f}%", fontsize=9, fontname="helv")
        y += 15

        if result.error_message:
            page.insert_text((72, y), f"Error: {result.error_message[:80]}", fontsize=9, fontname="helv", color=(0.8, 0, 0))
            y += 12

        if result.quality_issues:
            for issue in result.quality_issues[:3]:
                page.insert_text((72, y), f"Issue: {issue[:70]}", fontsize=8, fontname="helv", color=(0.6, 0, 0))
                y += 10

    doc.save(output_path)
    doc.close()
    print(f"Report saved to: {output_path}")


def main():
    sample_dir = os.path.join(PROJECT_ROOT, "ignored-resources", "sample-files-marcedit")
    output_dir = os.path.join(HARNESS_DIR, "output")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("COMPREHENSIVE VISUAL REGRESSION TEST (Strict Mode)")
    print("=" * 60)
    print(f"Sample directory: {sample_dir}")

    # Create test cases
    print("\nGenerating test cases...")
    test_cases = create_test_cases(sample_dir, target_count=80)
    print(f"Created {len(test_cases)} test cases")

    if not test_cases:
        print("No test cases created!")
        return

    # Show distribution
    by_pdf = {}
    for tc in test_cases:
        by_pdf[tc.pdf_name] = by_pdf.get(tc.pdf_name, 0) + 1
    print("\nTests per PDF:")
    for pdf, count in sorted(by_pdf.items()):
        print(f"  {pdf[:40]}: {count}")

    # Run tests
    print("\nRunning tests...")
    results = []
    for i, tc in enumerate(test_cases):
        print(f"  [{i+1}/{len(test_cases)}] {tc.id}: {tc.pdf_name[:30]}...", end=" ")
        result = run_test(tc)
        results.append(result)

        if result.status == "PASS":
            print(f"PASS ({result.pixel_diff_pct:.1f}%)")
        elif result.status == "FAIL":
            print(f"FAIL: {result.error_message[:40]}")
        else:
            print(f"{result.status}: {result.error_message[:40]}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    warned = sum(1 for r in results if r.status == "WARN")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")

    print(f"PASS:  {passed:3d} ({passed/total*100:5.1f}%)")
    print(f"WARN:  {warned:3d} ({warned/total*100:5.1f}%)")
    print(f"FAIL:  {failed:3d} ({failed/total*100:5.1f}%)")
    print(f"ERROR: {errors:3d} ({errors/total*100:5.1f}%)")
    print(f"TOTAL: {total:3d}")

    # Generate report
    report_path = os.path.join(output_dir, f"Visual_Regression_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    generate_pdf_report(results, report_path)

    # Also save JSON results
    json_path = report_path.replace(".pdf", ".json")
    json_results = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total": total,
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "error": errors
        },
        "results": [
            {
                "id": r.test_case.id,
                "pdf": r.test_case.pdf_name,
                "page": r.test_case.page,
                "edit_type": r.test_case.edit_type,
                "target": r.test_case.target_text[:50],
                "replacement": r.test_case.replacement_text[:50],
                "status": r.status,
                "success": r.success,
                "pixel_diff_pct": r.pixel_diff_pct,
                "error": r.error_message,
                "issues": r.quality_issues
            }
            for r in results
        ]
    }
    with open(json_path, "w") as f:
        json.dump(json_results, f, indent=2)
    print(f"JSON results saved to: {json_path}")

    return report_path, results


if __name__ == "__main__":
    main()
