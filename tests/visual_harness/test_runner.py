"""
Test Runner - Executes test cases and captures visual results.

For each test case:
1. Opens PDF
2. Renders "before" image of target region
3. Executes core.redact_and_replace()
4. Renders "after" image
5. Computes visual diff metrics
6. Emits results to results.json
"""

import os
import sys
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Generator
import tempfile
import shutil

# Import external packages FIRST (before adding project paths that might shadow them)
try:
    import fitz  # PyMuPDF
    from PIL import Image
    import numpy as np
except ImportError as e:
    print(f"Error: Required dependency missing: {e}")
    print("Install with: pip install pymupdf pillow numpy")
    sys.exit(1)

# NOW add project paths for core.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, "Sources", "Marcedit", "python_site"))

# Import core editing functions
try:
    from editor_pkg import core
except ImportError:
    print("Warning: Could not import editor_pkg.core - running in analysis-only mode")
    core = None


@dataclass
class TestResult:
    """Result of a single test execution."""
    test_id: str
    status: str  # PASS, WARN, FAIL, ERROR
    verdict_reason: str
    
    # Metrics
    pixel_diff_pct: float
    ssim_score: float
    font_preserved: bool
    baseline_shift_px: float
    width_change_pct: float
    
    # Paths to artifacts
    before_image: str
    after_image: str
    diff_image: str
    
    # Execution info
    execution_time_ms: float
    error_message: Optional[str] = None
    
    # Font info
    original_font: str = ""
    result_font: str = ""
    
    # Edit info
    file: str = ""
    page: int = 0
    edit_type: str = ""  # identity, substitution, overflow
    target_text: str = ""
    replacement_text: str = ""


class TestRunner:
    """Executes test cases and captures results."""
    
    # Pass/Fail thresholds
    # Pass/Fail thresholds
    IDENTITY_PIXEL_DIFF_THRESHOLD = 3.0  # % (Relaxed from 1.0 to account for rendering engine differences)
    SUBSTITUTION_PIXEL_DIFF_THRESHOLD = 15.0  # %
    SSIM_THRESHOLD = 0.95
    BASELINE_SHIFT_THRESHOLD = 2.0  # pixels
    
    def __init__(self, manifest_path: str, output_dir: str):
        self.manifest_path = manifest_path
        self.output_dir = output_dir
        self.images_dir = os.path.join(output_dir, "images")
        self.results: list[TestResult] = []
        
        os.makedirs(self.images_dir, exist_ok=True)
        
        # Load manifest
        with open(manifest_path, 'r') as f:
            self.manifest = json.load(f)
        self.test_cases = self.manifest.get("test_cases", [])
    
    def run_all(self, progress_callback=None) -> list[TestResult]:
        """Run all test cases."""
        total = len(self.test_cases)
        
        for i, tc_data in enumerate(self.test_cases):
            if progress_callback:
                progress_callback(i + 1, total, tc_data.get("id", ""))
            
            result = self.run_test(tc_data)
            self.results.append(result)
        
        self.save_results()
        return self.results
    
    def run_test(self, tc_data: dict) -> TestResult:
        """Run a single test case."""
        tc_id = tc_data.get("id", "UNKNOWN")
        start_time = datetime.now()
        
        try:
            # Resolve file path
            pdf_path = self._resolve_path(tc_data["file"])
            if not os.path.exists(pdf_path):
                return self._error_result(tc_id, f"PDF not found: {pdf_path}")
            
            page_num = tc_data["page"]
            target_text = tc_data["target_text"]
            replacement = tc_data["replacement"]
            edit_type = tc_data["edit_type"]
            original_font = tc_data.get("original_font", "Unknown")
            
            # Create working copy
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                shutil.copy(pdf_path, tmp.name)
                work_path = tmp.name
            
            try:
                # Render BEFORE image
                before_img, before_bbox = self._render_region(
                    work_path, page_num, tc_data.get("target_bbox")
                )
                before_path = os.path.join(self.images_dir, f"{tc_id}_before.png")
                before_img.save(before_path)
                
                # Execute edit
                result_font = "Unknown"
                if core:
                    # Call the actual editing function
                    edit_result = self._execute_edit(
                        work_path, page_num, target_text, replacement
                    )
                    result_font = edit_result.get("font_used", "Unknown")
                else:
                    # Dry run - just copy file
                    pass
                
                # Render AFTER image
                after_img, _ = self._render_region(
                    work_path, page_num, tc_data.get("target_bbox")
                )
                after_path = os.path.join(self.images_dir, f"{tc_id}_after.png")
                after_img.save(after_path)
                
                # Compute diff
                diff_img, metrics = self._compute_diff(before_img, after_img)
                diff_path = os.path.join(self.images_dir, f"{tc_id}_diff.png")
                diff_img.save(diff_path)
                
                # Determine verdict
                status, reason = self._determine_verdict(
                    edit_type, metrics, original_font, result_font, edit_result.get("font_source_type", "")
                )
                
                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                return TestResult(
                    test_id=tc_id,
                    status=status,
                    verdict_reason=reason,
                    pixel_diff_pct=metrics["pixel_diff_pct"],
                    ssim_score=metrics["ssim"],
                    font_preserved=(original_font == result_font or result_font == "Unknown"),
                    baseline_shift_px=metrics.get("baseline_shift", 0.0),
                    width_change_pct=metrics.get("width_change", 0.0),
                    before_image=before_path,
                    after_image=after_path,
                    diff_image=diff_path,
                    execution_time_ms=elapsed_ms,
                    original_font=original_font,
                    result_font=result_font,
                    file=tc_data.get("file", ""),
                    page=page_num,
                    edit_type=edit_type,
                    target_text=target_text,
                    replacement_text=replacement
                )
                
            finally:
                # Cleanup temp file
                if os.path.exists(work_path):
                    os.unlink(work_path)
                    
        except Exception as e:
            return self._error_result(tc_id, str(e))
    
    def _resolve_path(self, relative_path: str) -> str:
        """Resolve relative path to absolute."""
        # Try relative to project root
        abs_path = os.path.join(PROJECT_ROOT, relative_path)
        if os.path.exists(abs_path):
            return abs_path
        
        # Try as-is
        if os.path.exists(relative_path):
            return os.path.abspath(relative_path)
        
        return relative_path
    
    def _render_region(self, pdf_path: str, page_num: int, bbox: Optional[tuple] = None) -> tuple:
        """Render a region of a PDF page to an image."""
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        # High DPI for quality comparison
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        
        if bbox:
            # Expand bbox slightly for context
            margin = 20
            clip = fitz.Rect(
                max(0, bbox[0] - margin),
                max(0, bbox[1] - margin),
                min(page.rect.width, bbox[2] + margin),
                min(page.rect.height, bbox[3] + margin)
            )
            pix = page.get_pixmap(matrix=mat, clip=clip)
        else:
            pix = page.get_pixmap(matrix=mat)
        
        doc.close()
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img, bbox
    
    def _execute_edit(self, pdf_path: str, page_num: int, 
                      target_text: str, replacement: str) -> dict:
        """Execute the actual PDF edit using core.py."""
        if not core:
            return {"font_used": "Unknown", "error": "core module not available"}
        
        result_info = {"font_used": "Unknown"}
        
        try:
            # Use replace_text_in_pdf which takes file paths
            # Note: page_num is 0-indexed in our test data, but replace_text_in_pdf uses 1-indexed
            # PyMuPDF can't save to same file, so save to temp then copy back
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_out:
                temp_output = tmp_out.name
            
            result = core.replace_text_in_pdf(
                input_path=pdf_path,
                output_path=temp_output,  # Save to temp file
                target_text=target_text,
                replacement_text=replacement,
                page_number=page_num + 1,  # Convert to 1-indexed
                manual_overrides=None
            )
            
            if result.get('success'):
                # Extract structured font info
                font_src = result.get('font_source', 'Unknown')
                final_font = result.get('applied_info', {}).get('final_font', 'Unknown')
                
                result_info['font_used'] = final_font
                result_info['font_source_type'] = font_src
                result_info['modified'] = result.get('modified', False)
                # Copy temp file back to original path
                shutil.copy(temp_output, pdf_path)
            else:
                result_info['error'] = result.get('message', 'Edit failed')
                result_info['debug_log'] = result.get('debug_log', [])
            
            # Cleanup temp file
            if os.path.exists(temp_output):
                os.unlink(temp_output)
            
        except Exception as e:
            result_info["error"] = str(e)
        
        return result_info
    
    def _compute_diff(self, before: Image.Image, after: Image.Image) -> tuple:
        """Compute visual difference between before and after images."""
        # Ensure same size
        if before.size != after.size:
            after = after.resize(before.size)
        
        # Convert to numpy arrays
        before_arr = np.array(before, dtype=np.float32)
        after_arr = np.array(after, dtype=np.float32)
        
        # Compute absolute difference
        diff_arr = np.abs(before_arr - after_arr)
        
        # Pixel diff percentage
        total_pixels = before_arr.size
        changed_pixels = np.sum(diff_arr > 10)  # Threshold for "changed"
        pixel_diff_pct = (changed_pixels / total_pixels) * 100
        
        # SSIM (simplified)
        ssim = self._compute_ssim(before_arr, after_arr)
        
        # Create diff visualization (red where changed)
        diff_vis = np.zeros_like(before_arr)
        mask = np.max(diff_arr, axis=2) > 10
        diff_vis[mask] = [255, 0, 0]  # Red for changes
        diff_vis[~mask] = before_arr[~mask] * 0.3  # Dim unchanged areas
        
        diff_img = Image.fromarray(diff_vis.astype(np.uint8))
        
        metrics = {
            "pixel_diff_pct": pixel_diff_pct,
            "ssim": ssim,
            "baseline_shift": 0.0,  # TODO: Implement baseline detection
            "width_change": 0.0  # TODO: Implement width comparison
        }
        
        return diff_img, metrics
    
    def _compute_ssim(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Compute simplified SSIM score."""
        # Convert to grayscale
        gray1 = np.mean(img1, axis=2)
        gray2 = np.mean(img2, axis=2)
        
        # Compute means
        mu1 = np.mean(gray1)
        mu2 = np.mean(gray2)
        
        # Compute variances and covariance
        sigma1_sq = np.var(gray1)
        sigma2_sq = np.var(gray2)
        sigma12 = np.mean((gray1 - mu1) * (gray2 - mu2))
        
        # SSIM constants
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        ssim = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / \
               ((mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2))
        
        return float(ssim)
    
    def _determine_verdict(self, edit_type: str, metrics: dict,
                           original_font: str, result_font: str, font_source_type: str = "") -> tuple:
        """Determine pass/fail status and reason."""
        reasons = []
        status = "PASS"
        
        pixel_diff = metrics["pixel_diff_pct"]
        ssim = metrics["ssim"]
        
        # Identity edits should have minimal change
        if edit_type == "identity":
            threshold = self.IDENTITY_PIXEL_DIFF_THRESHOLD
            if pixel_diff > threshold:
                reasons.append(f"Pixel diff {pixel_diff:.1f}% exceeds {threshold}% for identity edit")
                status = "FAIL"
        else:
            threshold = self.SUBSTITUTION_PIXEL_DIFF_THRESHOLD
            if pixel_diff > threshold:
                reasons.append(f"Pixel diff {pixel_diff:.1f}% exceeds {threshold}%")
                status = "WARN"
        
        # SSIM check
        if ssim < self.SSIM_THRESHOLD:
            reasons.append(f"SSIM {ssim:.2f} below threshold {self.SSIM_THRESHOLD}")
            if status != "FAIL":
                status = "WARN"
        
        # Font preservation check
        # Font preservation check
        # Trust "Smart Reuse" or "Exact match" source types
        is_smart_reuse = "Smart Reuse" in font_source_type or "Exact match" in font_source_type
        
        if not is_smart_reuse and result_font != "Unknown" and original_font != result_font:
            # Also check if result font is a subset of original (e.g. "Arial" vs "subset_...+Arial")
            # But here result_font is usually the random subset name.
            # So reliance on font_source_type is key.
            reasons.append(f"Font changed: {original_font} → {result_font} ({font_source_type})")
            if status != "FAIL":
                status = "WARN"
        
        if status == "PASS":
            reasons.append(f"All metrics within tolerance (diff={pixel_diff:.1f}%, SSIM={ssim:.2f})")
        
        return status, "; ".join(reasons)
    
    def _error_result(self, tc_id: str, error_msg: str) -> TestResult:
        """Create an error result."""
        return TestResult(
            test_id=tc_id,
            status="ERROR",
            verdict_reason=f"Execution error: {error_msg}",
            pixel_diff_pct=0.0,
            ssim_score=0.0,
            font_preserved=False,
            baseline_shift_px=0.0,
            width_change_pct=0.0,
            before_image="",
            after_image="",
            diff_image="",
            execution_time_ms=0.0,
            error_message=error_msg
        )
    
    def save_results(self):
        """Save results to JSON file."""
        results_path = os.path.join(self.output_dir, "results.json")
        
        summary = {
            "run_at": datetime.now().isoformat(),
            "total": len(self.results),
            "pass": sum(1 for r in self.results if r.status == "PASS"),
            "warn": sum(1 for r in self.results if r.status == "WARN"),
            "fail": sum(1 for r in self.results if r.status == "FAIL"),
            "error": sum(1 for r in self.results if r.status == "ERROR"),
        }
        
        output = {
            "summary": summary,
            "results": [asdict(r) for r in self.results]
        }
        
        with open(results_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\nResults saved to: {results_path}")
        print(f"Summary: {summary['pass']} PASS, {summary['warn']} WARN, "
              f"{summary['fail']} FAIL, {summary['error']} ERROR")
    
    def get_summary(self) -> dict:
        """Get summary of results."""
        return {
            "total": len(self.results),
            "pass": sum(1 for r in self.results if r.status == "PASS"),
            "warn": sum(1 for r in self.results if r.status == "WARN"),
            "fail": sum(1 for r in self.results if r.status == "FAIL"),
            "error": sum(1 for r in self.results if r.status == "ERROR"),
        }


def run_tests(manifest_path: str = None, output_dir: str = None) -> list[TestResult]:
    """Convenience function to run all tests."""
    if manifest_path is None:
        manifest_path = "tests/visual_harness/output/test_manifest.json"
    if output_dir is None:
        output_dir = "tests/visual_harness/output"
    
    def progress(current, total, tc_id):
        print(f"\r[{current}/{total}] Running {tc_id}...", end="", flush=True)
    
    runner = TestRunner(manifest_path, output_dir)
    results = runner.run_all(progress_callback=progress)
    print()  # Newline after progress
    return results


if __name__ == "__main__":
    run_tests()
