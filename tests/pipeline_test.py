"""
Test PDF text replacement pipeline using editor_pkg.core module.
Tests basic text replacement and error handling for missing text.
"""
import unittest
import os
import tempfile
import sys
from pathlib import Path

# Import reportlab FIRST (before adding editor path to avoid PIL conflict)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Add python_site to path AFTER reportlab imports
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(PROJECT_ROOT / "Sources" / "Marcedit" / "python_site"))

from editor_pkg.core import replace_text_in_pdf


class TestPDFPipeline(unittest.TestCase):
    """Test PDF text replacement pipeline using editor_pkg.core."""
    
    def setUp(self):
        """Create temp directory and simple test PDF."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_pdf_in = os.path.join(self.temp_dir, "test_input.pdf")
        self.test_pdf_out = os.path.join(self.temp_dir, "test_output.pdf")
        
        # Create a simple PDF using reportlab
        c = canvas.Canvas(self.test_pdf_in, pagesize=letter)
        c.drawString(100, 750, "Hello World this is a test.")
        c.drawString(100, 730, "Line to edit matches this.")
        c.save()

    def tearDown(self):
        """Cleanup temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_basic_replacement(self):
        """Test replacing 'World' with 'Marcedit'"""
        target = "World"
        replacement = "Marcedit"
        
        # Call the replace function directly
        result = replace_text_in_pdf(
            self.test_pdf_in,
            self.test_pdf_out,
            target,
            replacement,
            page_number=1
        )
        
        # Check result
        self.assertTrue(result.get("success", False), f"Replacement failed: {result}")
        
        # Verify output exists
        self.assertTrue(os.path.exists(self.test_pdf_out), "Output PDF not created")
        
        # Verify original text removed from output
        import fitz
        doc = fitz.open(self.test_pdf_out)
        page = doc[0]
        # Check that "World" is no longer present
        old_rects = page.search_for("World")
        doc.close()
        self.assertEqual(len(old_rects), 0, "Original text 'World' still found in output")

    def test_replacement_not_found(self):
        """Test searching for text that doesn't exist"""
        target = "NonExistentText12345"
        replacement = "Void"
        
        result = replace_text_in_pdf(
            self.test_pdf_in,
            self.test_pdf_out,
            target,
            replacement,
            page_number=1
        )
        
        # Should return success=False or have message about not found
        if result.get("success"):
            # Some implementations return success with a message
            self.assertIn("not found", result.get("message", "").lower())
        else:
            # Expected - text not found returns failure
            pass

if __name__ == '__main__':
    unittest.main()
