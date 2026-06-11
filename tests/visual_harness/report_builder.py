"""
Report Builder - Generates visual PDF report from test results.

Creates a multi-page PDF with:
- Summary page (pass/fail counts, critical failures)
- Detail pages for each test (before/after/diff images + explanation)
"""

import os
import json
from datetime import datetime
from typing import Optional

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
        PageBreak, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
except ImportError:
    print("Error: reportlab required. Install with: pip install reportlab")
    raise


class ReportBuilder:
    """Builds PDF report from test results."""
    
    def __init__(self, results_path: str, output_path: str):
        self.results_path = results_path
        self.output_path = output_path
        
        # Load results
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        self.summary = data.get("summary", {})
        self.results = data.get("results", [])
        
        # Setup styles
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Create custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='TestHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=6,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='PassStyle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.darkgreen,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='FailStyle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.darkred,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='WarnStyle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.orange,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='Explanation',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=20,
            textColor=colors.gray
        ))
    
    def build(self):
        """Build the PDF report."""
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        story = []
        
        # Summary page
        story.extend(self._build_summary_page())
        story.append(PageBreak())
        
        # Detail pages
        for result in self.results:
            story.extend(self._build_detail_page(result))
            story.append(PageBreak())
        
        # Build PDF
        doc.build(story)
        print(f"Report generated: {self.output_path}")
    
    def _build_summary_page(self) -> list:
        """Build the summary page content."""
        content = []
        
        # Title
        content.append(Paragraph(
            "Visual Regression Report",
            self.styles['Title']
        ))
        content.append(Spacer(1, 12))
        
        # Run info
        run_date = self.summary.get("run_at", datetime.now().isoformat())
        content.append(Paragraph(
            f"Generated: {run_date}",
            self.styles['Normal']
        ))
        content.append(Spacer(1, 24))
        
        # Summary table
        total = self.summary.get("total", 0)
        passed = self.summary.get("pass", 0)
        warned = self.summary.get("warn", 0)
        failed = self.summary.get("fail", 0)
        errors = self.summary.get("error", 0)
        
        summary_data = [
            ["Status", "Count", "Percentage"],
            ["PASS", str(passed), f"{100*passed/max(total,1):.1f}%"],
            ["WARN", str(warned), f"{100*warned/max(total,1):.1f}%"],
            ["FAIL", str(failed), f"{100*failed/max(total,1):.1f}%"],
            ["ERROR", str(errors), f"{100*errors/max(total,1):.1f}%"],
            ["TOTAL", str(total), "100%"],
        ]
        
        table = Table(summary_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, 1), colors.lightgreen),
            ('BACKGROUND', (0, 2), (-1, 2), colors.lightyellow),
            ('BACKGROUND', (0, 3), (-1, 3), colors.lightcoral),
            ('BACKGROUND', (0, 4), (-1, 4), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        content.append(table)
        content.append(Spacer(1, 24))
        
        # Critical failures list
        failures = [r for r in self.results if r.get("status") in ("FAIL", "ERROR")]
        if failures:
            content.append(Paragraph(
                "Critical Failures:",
                self.styles['Heading2']
            ))
            for r in failures[:20]:  # Limit to 20
                tc_id = r.get("test_id", "?")
                reason = r.get("verdict_reason", "Unknown reason")[:100]
                content.append(Paragraph(
                    f"• <b>{tc_id}</b>: {reason}",
                    self.styles['Normal']
                ))
            content.append(Spacer(1, 12))
        
        return content
    
    def _build_detail_page(self, result: dict) -> list:
        """Build a detail page for a single test result."""
        content = []
        
        tc_id = result.get("test_id", "?")
        status = result.get("status", "?")
        
        # Header with test ID and status
        status_style = {
            "PASS": self.styles['PassStyle'],
            "WARN": self.styles['WarnStyle'],
            "FAIL": self.styles['FailStyle'],
            "ERROR": self.styles['FailStyle']
        }.get(status, self.styles['Normal'])
        
        header_text = f"{tc_id}: {status}"
        content.append(Paragraph(header_text, status_style))
        content.append(Spacer(1, 6))
        
        # Test info
        file_name = os.path.basename(result.get("file", "unknown"))
        page_num = result.get('page', '?')
        content.append(Paragraph(
            f"File: {file_name} | Page: {page_num}",
            self.styles['Normal']
        ))
        content.append(Paragraph(
            f"Font: {result.get('original_font', '?')} → {result.get('result_font', '?')}",
            self.styles['Normal']
        ))
        
        # Edit info - show type and text change
        edit_type = result.get('edit_type', 'unknown')
        target = result.get('target_text', '')[:50]  # Truncate long text
        replacement = result.get('replacement_text', '')[:50]
        
        # Determine display type
        if edit_type == 'identity':
            display_type = "Identity"
            edit_desc = f"\"{target}\" (no change)"
        elif edit_type == 'substitution':
            display_type = "Change"
            edit_desc = f"\"{target}\" → \"{replacement}\""
        elif edit_type == 'overflow':
            display_type = "Add"
            edit_desc = f"\"{target}\" → \"{replacement}\""
        else:
            display_type = edit_type.title()
            edit_desc = f"\"{target}\" → \"{replacement}\""
        
        content.append(Paragraph(
            f"Edit: <b>{display_type}</b> | {edit_desc}",
            self.styles['Normal']
        ))
        content.append(Spacer(1, 12))
        
        # Images (Before | After | Diff) - preserve aspect ratio
        images_row = []
        max_img_width = 2.2 * inch
        max_img_height = 2.0 * inch
        
        for img_key, label in [("before_image", "BEFORE"), 
                                ("after_image", "AFTER"), 
                                ("diff_image", "DIFF")]:
            img_path = result.get(img_key, "")
            if img_path and os.path.exists(img_path):
                try:
                    # Get actual image dimensions to preserve aspect ratio
                    from PIL import Image as PILImage
                    with PILImage.open(img_path) as pil_img:
                        orig_w, orig_h = pil_img.size
                    
                    # Scale to fit within max bounds while preserving aspect ratio
                    scale_w = max_img_width / orig_w if orig_w > 0 else 1
                    scale_h = max_img_height / orig_h if orig_h > 0 else 1
                    scale = min(scale_w, scale_h)
                    
                    final_w = orig_w * scale
                    final_h = orig_h * scale
                    
                    img = Image(img_path, width=final_w, height=final_h)
                    images_row.append([Paragraph(f"<b>{label}</b>", self.styles['Normal']), img])
                except Exception as e:
                    images_row.append([Paragraph(f"<b>{label}</b>", self.styles['Normal']), 
                                      Paragraph(f"Error: {e}", self.styles['Normal'])])
            else:
                images_row.append([Paragraph(f"<b>{label}</b>", self.styles['Normal']),
                                  Paragraph("(no image)", self.styles['Normal'])])
        
        if images_row:
            # Create side-by-side table
            img_table = Table(
                [[r[0] for r in images_row], [r[1] for r in images_row]],
                colWidths=[max_img_width + 0.2*inch] * 3
            )
            img_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ]))
            content.append(img_table)
            content.append(Spacer(1, 12))
        
        # Metrics
        metrics_text = (
            f"Pixel Diff: {result.get('pixel_diff_pct', 0):.2f}% | "
            f"SSIM: {result.get('ssim_score', 0):.3f} | "
            f"Baseline Shift: {result.get('baseline_shift_px', 0):.1f}px"
        )
        content.append(Paragraph(metrics_text, self.styles['Normal']))
        content.append(Spacer(1, 6))
        
        # Explanation / Verdict reason
        verdict_reason = result.get("verdict_reason", "No explanation available")
        content.append(Paragraph(
            f"<b>Analysis:</b> {verdict_reason}",
            self.styles['Explanation']
        ))
        content.append(Spacer(1, 12))
        
        # Feedback prompt
        content.append(Paragraph(
            f"<i>Feedback: Reference this test as {tc_id} in your review.</i>",
            self.styles['Explanation']
        ))
        
        return content


def build_report(results_path: str = None, output_path: str = None):
    """Convenience function to build report."""
    if results_path is None:
        results_path = "tests/visual_harness/output/results.json"
    if output_path is None:
        output_path = "tests/visual_harness/output/Visual_Regression_Report.pdf"
    
    builder = ReportBuilder(results_path, output_path)
    builder.build()


if __name__ == "__main__":
    build_report()
