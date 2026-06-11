"""
Unit tests for font extraction logic in core.py

Tests the _extract_font_to_temp function's ability to correctly match
fonts by name while avoiding incorrect style/weight matches.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site'))

import unittest
from unittest.mock import MagicMock, patch
import tempfile


class TestFontStyleMatching(unittest.TestCase):
    """Test the font style matching logic used in _extract_font_to_temp"""
    
    # Comprehensive list of style markers (should match core.py)
    STYLE_MARKERS = [
        ',bold', '-bold', 'bold',
        ',light', '-light', 'light',
        ',medium', '-medium', 'medium',
        ',heavy', '-heavy', 'heavy', 
        ',black', '-black', 'black',
        ',thin', '-thin', 'thin',
        ',semibold', '-semibold', 'semibold',
        ',demibold', '-demibold', 'demibold',
        ',extrabold', '-extrabold', 'extrabold',
        ',ultralight', '-ultralight', 'ultralight',
        ',italic', '-italic', 'italic',
        ',oblique', '-oblique', 'oblique',
        ',condensed', '-condensed', 'condensed',
        ',narrow', '-narrow', 'narrow',
        ',extended', '-extended', 'extended',
        ',wide', '-wide', 'wide',
    ]
    
    def should_match(self, target: str, base: str) -> bool:
        """
        Simulate the matching logic from _extract_font_to_temp.
        Returns True if base should match target.
        """
        target_clean = target.split('+')[-1].lower() if '+' in target else target.lower()
        base_clean = base.split('+')[-1].lower() if '+' in base else base.lower()
        
        # Exact match
        if base_clean == target_clean:
            return True
        
        # Substring match with style exclusion
        if target_clean in base_clean:
            has_unwanted_style = any(
                marker in base_clean 
                for marker in self.STYLE_MARKERS 
                if marker not in target_clean
            )
            if not has_unwanted_style:
                return True
        
        return False

    # === EXACT MATCH TESTS ===
    
    def test_exact_match_simple(self):
        """Exact font name match should succeed"""
        self.assertTrue(self.should_match('TimesNewRoman', 'TimesNewRoman'))
    
    def test_exact_match_with_subset_prefix(self):
        """Match should work with subset prefix like BLUVWU+"""
        self.assertTrue(self.should_match('BLUVWU+TimesNewRoman', 'ABCDEF+TimesNewRoman'))
    
    def test_exact_match_case_insensitive(self):
        """Match should be case insensitive"""
        self.assertTrue(self.should_match('timesnewroman', 'TIMESNEWROMAN'))
    
    # === STYLE EXCLUSION TESTS ===
    
    def test_reject_bolditalic_when_regular_wanted(self):
        """Should NOT match BoldItalic when Regular is requested"""
        self.assertFalse(self.should_match('TimesNewRoman', 'TimesNewRoman,BoldItalic'))
    
    def test_reject_bold_when_regular_wanted(self):
        """Should NOT match Bold when Regular is requested"""
        self.assertFalse(self.should_match('TimesNewRoman', 'TimesNewRoman,Bold'))
        self.assertFalse(self.should_match('TimesNewRoman', 'TimesNewRoman-Bold'))
        self.assertFalse(self.should_match('Arial', 'ArialBold'))
    
    def test_reject_italic_when_regular_wanted(self):
        """Should NOT match Italic when Regular is requested"""
        self.assertFalse(self.should_match('TimesNewRoman', 'TimesNewRoman,Italic'))
        self.assertFalse(self.should_match('TimesNewRoman', 'TimesNewRoman-Italic'))
    
    def test_reject_oblique_when_regular_wanted(self):
        """Should NOT match Oblique when Regular is requested"""
        self.assertFalse(self.should_match('Helvetica', 'Helvetica-Oblique'))
    
    def test_reject_light_when_regular_wanted(self):
        """Should NOT match Light when Regular is requested"""
        self.assertFalse(self.should_match('Roboto', 'Roboto-Light'))
        self.assertFalse(self.should_match('Roboto', 'RobotoLight'))
    
    def test_reject_semibold_when_regular_wanted(self):
        """Should NOT match SemiBold when Regular is requested"""
        self.assertFalse(self.should_match('OpenSans', 'OpenSans-SemiBold'))
    
    def test_reject_condensed_when_regular_wanted(self):
        """Should NOT match Condensed when Regular is requested"""
        self.assertFalse(self.should_match('Arial', 'Arial-Condensed'))
        self.assertFalse(self.should_match('Arial', 'ArialNarrow'))
    
    # === ALLOWED MATCHES TESTS ===
    
    def test_allow_regular_suffix(self):
        """Should match fonts with -Regular suffix"""
        self.assertTrue(self.should_match('TimesNewRoman', 'TimesNewRoman-Regular'))
    
    def test_allow_mt_suffix(self):
        """Should match fonts with MT (Mac TrueType) suffix"""
        self.assertTrue(self.should_match('Arial', 'ArialMT'))
    
    def test_allow_ps_suffix(self):
        """Should match fonts with PS (PostScript) suffix"""
        self.assertTrue(self.should_match('TimesNewRoman', 'TimesNewRomanPS'))
    
    # === STYLE PRESERVATION TESTS ===
    
    def test_match_bold_when_bold_wanted(self):
        """Should match Bold when Bold is explicitly requested"""
        self.assertTrue(self.should_match('TimesNewRoman,Bold', 'TimesNewRoman,Bold'))
        self.assertTrue(self.should_match('TimesNewRoman-Bold', 'TimesNewRoman-Bold'))
    
    def test_match_italic_when_italic_wanted(self):
        """Should match Italic when Italic is explicitly requested"""
        self.assertTrue(self.should_match('TimesNewRoman,Italic', 'TimesNewRoman,Italic'))
    
    def test_match_bolditalic_when_bolditalic_wanted(self):
        """Should match BoldItalic when BoldItalic is explicitly requested"""
        self.assertTrue(self.should_match('TimesNewRoman,BoldItalic', 'TimesNewRoman,BoldItalic'))
    
    # === EDGE CASES ===
    
    def test_font_name_containing_bold_word(self):
        """Font names legitimately containing 'bold' should still work for exact match"""
        # e.g., a font actually named "BoldStreet" or "EmboldFont"
        self.assertTrue(self.should_match('BoldStreet', 'BoldStreet'))
    
    def test_partial_name_no_match(self):
        """Should not match if target is not a substring at all"""
        self.assertFalse(self.should_match('Times', 'Arial'))
    
    def test_subset_prefix_variation(self):
        """Different subset prefixes should still match"""
        self.assertTrue(self.should_match('AAAAAA+TimesNewRoman', 'ZZZZZZ+TimesNewRoman'))


class TestFontExtractionIntegration(unittest.TestCase):
    """Integration tests for _extract_font_to_temp with real PDFs"""
    
    def setUp(self):
        """Find test PDFs"""
        self.test_dir = os.path.dirname(__file__)
        self.project_root = os.path.dirname(self.test_dir)
        self.sample_dir = os.path.join(self.project_root, 'ignored-resources', 'sample-files')
    
    def test_extract_regular_not_bold(self):
        """Test that extracting TimesNewRoman gets Regular, not BoldItalic"""
        pdf_path = os.path.join(self.sample_dir, 'Redline - Fitness Center Term Sheet.pdf')
        
        if not os.path.exists(pdf_path):
            self.skipTest(f"Test PDF not found: {pdf_path}")
        
        from editor_pkg import core
        import fitz
        
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        # Request TimesNewRoman (Regular)
        result_path = core._extract_font_to_temp(doc, page, 'TimesNewRoman')
        
        self.assertIsNotNone(result_path, "Should extract a font")
        self.assertTrue(os.path.exists(result_path), "Extracted file should exist")
        
        # Verify it's NOT the BoldItalic variant
        font = fitz.Font(fontfile=result_path)
        self.assertIn('Regular', font.name, f"Should be Regular font, got: {font.name}")
        self.assertNotIn('BoldItalic', font.name, f"Should NOT be BoldItalic, got: {font.name}")
        
        doc.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
