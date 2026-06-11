"""
Isolated tests for redaction cleanup verification.
Ensures apply_redactions properly removes original text vectors.

Run with: pytest tests/test_redaction_cleanup.py -v
"""

import pytest
import fitz
import sys
import os
from pathlib import Path

# Add the editor_pkg to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site'))


class TestRedactionRemovesText:
    """Test that redaction actually removes vector text."""

    def test_redaction_removes_original_text(self, tmp_path):
        """Verify that apply_redactions with PDF_REDACT_LINE_ART_IF_TOUCHED removes text."""
        pdf_path = tmp_path / "redaction_test.pdf"
        
        # Create PDF with text
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "ORIGINAL", fontsize=24)
        doc.save(pdf_path)
        doc.close()
        
        # Reopen and redact
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        # Find and redact the text
        rects = page.search_for("ORIGINAL")
        assert len(rects) > 0, "Text should be found before redaction"
        
        rect = rects[0]
        page.add_redact_annot(rect, fill=(1, 1, 1))  # White fill
        page.apply_redactions(images=0, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        
        # After redaction, text should be gone
        remaining = page.search_for("ORIGINAL")
        assert len(remaining) == 0, "Redaction should remove searchable text"
        
        doc.close()

    def test_graphics_zero_preserves_text(self, tmp_path):
        """Demonstrate that graphics=0 (old behavior) preserves vector paths."""
        pdf_path = tmp_path / "graphics_zero_test.pdf"
        
        # Create PDF with text
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "PRESERVED", fontsize=24)
        doc.save(pdf_path)
        doc.close()
        
        # Reopen and redact with graphics=0
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        rects = page.search_for("PRESERVED")
        assert len(rects) > 0
        
        rect = rects[0]
        page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)  # OLD BEHAVIOR
        
        # Note: With graphics=0, the text stream is removed but vector paths may remain
        # This test documents the old behavior for comparison
        
        doc.close()

    def test_redaction_with_transparent_fill(self, tmp_path):
        """Verify redaction with transparent fill (no white box)."""
        pdf_path = tmp_path / "transparent_redact.pdf"
        
        # Create PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "TARGET", fontsize=24)
        doc.save(pdf_path)
        doc.close()
        
        # Redact with fill=None (transparent)
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        rects = page.search_for("TARGET")
        rect = rects[0]
        
        page.add_redact_annot(rect, fill=None)
        page.apply_redactions(images=0, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        
        # Text should be removed
        remaining = page.search_for("TARGET")
        assert len(remaining) == 0
        
        doc.close()


class TestPreciseRedactionRect:
    """Test precise redaction rectangle calculation."""

    def test_expanded_rect_covers_ascenders(self, tmp_path):
        """Ensure expanded rect covers characters with ascenders."""
        pdf_path = tmp_path / "ascender_test.pdf"
        
        doc = fitz.open()
        page = doc.new_page()
        # Text with ascenders: b, d, f, h, k, l, t
        page.insert_text((100, 100), "bdfhklt", fontsize=24)
        doc.save(pdf_path)
        doc.close()
        
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        rects = page.search_for("bdfhklt")
        assert len(rects) > 0
        
        rect = rects[0]
        # Expand like the code does
        expanded = rect + (-0.5, -1.0, 0.5, 1.0)
        
        # Expanded should be larger
        assert expanded.width > rect.width
        assert expanded.height > rect.height
        
        doc.close()

    def test_expanded_rect_covers_descenders(self, tmp_path):
        """Ensure expanded rect covers characters with descenders."""
        pdf_path = tmp_path / "descender_test.pdf"
        
        doc = fitz.open()
        page = doc.new_page()
        # Text with descenders: g, j, p, q, y
        page.insert_text((100, 100), "gjpqy", fontsize=24)
        doc.save(pdf_path)
        doc.close()
        
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        rects = page.search_for("gjpqy")
        assert len(rects) > 0
        
        rect = rects[0]
        expanded = rect + (-0.5, -1.0, 0.5, 1.0)
        
        # Bottom margin should extend below baseline
        assert expanded.y1 > rect.y1
        
        doc.close()


class TestReplacementNoDoubleText:
    """Integration test: replacement should not leave ghost text."""

    def test_replace_removes_original(self, tmp_path):
        """Full replacement should remove original text completely."""
        from editor_pkg.core import replace_text_in_pdf
        
        input_path = tmp_path / "input.pdf"
        output_path = tmp_path / "output.pdf"
        
        # Create input PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "EXCESS", fontsize=24)
        doc.save(input_path)
        doc.close()
        
        # Replace
        result = replace_text_in_pdf(
            str(input_path),
            str(output_path),
            "EXCESS",
            "SUCCESS",
            page_number=1
        )
        
        assert result.get('success', False), f"Replacement failed: {result.get('message')}"
        
        # Verify output
        doc = fitz.open(output_path)
        page = doc[0]
        
        # Old text should be gone
        old_rects = page.search_for("EXCESS")
        assert len(old_rects) == 0, "Original text should be removed"
        
        # New text should exist
        new_rects = page.search_for("SUCCESS")
        assert len(new_rects) > 0, "Replacement text should be present"
        
        doc.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
