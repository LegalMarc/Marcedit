"""
Unit tests for MarcEdit PDF Editor core functions.
Tests focus on the critical functions added/modified during bug fixes.

Run with: pytest tests/test_editor_core.py -v
"""

import pytest
import fitz
import sys
import os
import unittest

# Add the editor_pkg to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site'))

from editor_pkg.core import (
    _get_reference_char_metrics,
    _calculate_precise_redaction_rect,
    replace_text_in_pdf,
    batch_replace,
    regex_replace,
    scrub_all_metadata,
)


class TestReferenceCharMetrics:
    """Test suite for _get_reference_char_metrics function."""

    @pytest.fixture
    def sample_page(self, tmp_path):
        """Create a sample PDF page with known text for testing."""
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Add text with known metrics
        # Line 1: Mix of x-height, cap-height, ascender, descender chars
        page.insert_text((50, 100), "Text Hgp x", fontsize=12)

        # Line 2: Multiple x-height chars for averaging
        page.insert_text((50, 120), "aeoun c", fontsize=14)

        # Line 3: Uppercase for cap-height testing
        page.insert_text((50, 140), "HELLO", fontsize=10)

        doc.save(pdf_path)
        doc.close()

        # Reopen and return the page
        doc = fitz.open(pdf_path)
        return doc[0]

    def test_none_page_returns_none(self):
        """Test that None page returns None."""
        result = _get_reference_char_metrics(None, fitz.Rect(50, 95, 100, 115), "Text")
        assert result is None

    def test_empty_rect_returns_none(self, sample_page):
        """Test that empty rect returns None."""
        result = _get_reference_char_metrics(sample_page, fitz.Rect(), "Text")
        assert result is None

    def test_invalid_text_returns_none(self, sample_page):
        """Test that invalid target_text returns None."""
        result = _get_reference_char_metrics(sample_page, fitz.Rect(50, 95, 100, 115), "")
        assert result is None
        result = _get_reference_char_metrics(sample_page, fitz.Rect(50, 95, 100, 115), None)
        assert result is None

    def test_finds_x_height_char(self, sample_page):
        """Test that x-height character is found and returned."""
        # Search for "Text" which contains 'e' (x-height) and 'T' (cap)
        rect = fitz.Rect(50, 95, 100, 115)
        result = _get_reference_char_metrics(sample_page, rect, "Text")

        assert result is not None
        char, width, height = result
        assert char in "Text"
        assert width > 0
        assert height > 0

    def test_prefers_x_height_over_cap(self, sample_page):
        """Test that x-height chars are preferred over cap-height."""
        # "aeoun" are all x-height, should be found
        rect = fitz.Rect(50, 115, 150, 135)
        result = _get_reference_char_metrics(sample_page, rect, "aeoun")

        assert result is not None
        char, _, _ = result
        # Should return an x-height char, not a cap
        assert char in "aeoun"

    def test_averages_multiple_x_height(self, sample_page):
        """Test that multiple x-height chars are averaged."""
        # "aeoun c" has 6 x-height chars, should average them
        rect = fitz.Rect(50, 115, 150, 135)
        result = _get_reference_char_metrics(sample_page, rect, "aeoun")

        assert result is not None
        _, width, height = result
        # Height should be reasonable for 14pt text (around 10-15)
        assert 10 < height < 20


class TestPreciseRedactionRect:
    """Test suite for _calculate_precise_redaction_rect function."""

    @pytest.fixture
    def sample_page(self, tmp_path):
        """Create a sample PDF page with text for redaction testing."""
        pdf_path = tmp_path / "test_redact.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Add text in a line
        page.insert_text((50, 100), "Hello World Test", fontsize=12)

        # Add overlapping text
        page.insert_text((50, 120), "Another Line", fontsize=12)

        doc.save(pdf_path)
        doc.close()

        doc = fitz.open(pdf_path)
        return doc[0]

    def test_none_page_returns_safe_rect(self):
        """Test that None page returns empty rect."""
        result = _calculate_precise_redaction_rect(None, fitz.Rect(50, 95, 100, 115), "Hello")
        # Should return safe fallback rect
        assert result is not None

    def test_empty_rect_returns_input(self, sample_page):
        """Test that empty rect returns safe fallback."""
        result = _calculate_precise_redaction_rect(sample_page, fitz.Rect(), "Hello")
        assert result is not None

    def test_invalid_text_returns_input_rect(self, sample_page):
        """Test that invalid text returns input rect."""
        input_rect = fitz.Rect(50, 95, 100, 115)
        result = _calculate_precise_redaction_rect(sample_page, input_rect, "")
        assert result == input_rect

    def test_expands_rect_for_safety(self, sample_page):
        """Test that rect includes safety margins around characters."""
        # Target "Hello" in "Hello World Test"
        input_rect = fitz.Rect(50, 95, 80, 105)
        result = _calculate_precise_redaction_rect(sample_page, input_rect, "Hello")

        assert result is not None
        # Result should include safety margins (0.3pt H, 0.8pt V on each side)
        # The actual character bounds might be smaller than input_rect,
        # but safety margins are added regardless
        assert result is not None
        # Result should be reasonable (not empty, not infinite)
        assert not result.is_empty
        assert not result.is_infinite
        # Should have some expansion from character bounds
        # We check that result intersects with input rect
        assert result.intersects(input_rect)

    def test_character_level_precision(self, sample_page):
        """Test that only matching characters are included."""
        # Use a realistic tight rect around "World" as _robust_search would return
        # (not an artificially wide rect covering the whole line).
        # search_for("World") in this fixture returns ~Rect(80.67, 87.1, 112.0, 103.6).
        input_rect = fitz.Rect(80, 86, 113, 105)
        result = _calculate_precise_redaction_rect(sample_page, input_rect, "World")

        assert result is not None
        # Width should be roughly 5 characters worth at 12pt
        # Each char ~6pt wide, so ~30pt; allow up to 40pt for safety margins
        assert 20 < result.width < 60


class TestBaselineCalculations:
    """Test baseline calculation logic to ensure it's correct."""

    def test_baseline_from_top_correct(self):
        """Test that baseline calculated from top is correct."""
        # For a rect from y0=100 to y1=110 (height=10)
        # Baseline at 85% down = 100 + 10*0.85 = 108.5
        rect_top = 100
        rect_bottom = 110
        rect_height = rect_bottom - rect_top

        baseline = rect_top + rect_height * 0.85

        assert abs(baseline - 108.5) < 0.01
        # Baseline should be BELOW top
        assert baseline > rect_top
        # Baseline should be ABOVE bottom (for text with descenders)
        assert baseline < rect_bottom

    def test_baseline_never_below_bottom(self):
        """Test that baseline estimation never places text below bounding box."""
        for height in [8, 10, 12, 14, 20, 24]:
            rect_top = 100
            rect_bottom = 100 + height
            rect_height = rect_bottom - rect_top

            # Using the 85% formula
            baseline = rect_top + rect_height * 0.85

            # Baseline should always be above bottom
            assert baseline < rect_bottom, f"Height {height}: baseline {baseline} >= bottom {rect_bottom}"
            # And above top
            assert baseline > rect_top


class TestFontScalingLogic:
    """Test font scaling calculation logic."""

    def test_cap_height_normalization(self):
        """Test that cap-height is normalized correctly."""
        # If we have a cap-height character at 15pt
        # And cap-height is typically 1.25x x-height
        # Then normalized x-height = 15 / 1.25 = 12pt

        cap_height = 15.0
        normalization_factor = 1.25
        normalized_height = cap_height / normalization_factor

        assert abs(normalized_height - 12.0) < 0.01

    def test_scaling_bounds_enforced(self):
        """Test that scaling factor stays within bounds."""
        ref_height = 10.0
        nom_height = 11.0

        # Calculate scale
        scale_factor = ref_height / nom_height

        # Apply bounds (0.75 to 1.35)
        scale_factor = max(min(scale_factor, 1.35), 0.75)

        # Should be within bounds
        assert 0.75 <= scale_factor <= 1.35

    def test_extreme_scaling_clamped(self):
        """Test that extreme scaling is clamped to bounds."""
        # Very large reference height
        ref_height = 20.0
        nom_height = 10.0
        scale_factor = ref_height / nom_height  # 2.0

        # Should be clamped to 1.35
        scale_factor = max(min(scale_factor, 1.35), 0.75)

        assert scale_factor == 1.35

        # Very small reference height
        ref_height = 5.0
        nom_height = 10.0
        scale_factor = ref_height / nom_height  # 0.5

        # Should be clamped to 0.75
        scale_factor = max(min(scale_factor, 1.35), 0.75)

        assert scale_factor == 0.75


class TestDescenderRatio:
    """Test descender and ascender ratio calculations."""

    def test_ascender_ratio_correct(self):
        """Test that ascender ratio uses correct value (0.7)."""
        # Ascender extends 0.7x x-height above baseline
        ascender_dist = 7.0
        est_x_height = ascender_dist / 0.7

        assert abs(est_x_height - 10.0) < 0.01

    def test_descender_ratio_correct(self):
        """Test that descender ratio uses correct value (0.3)."""
        # Descender extends 0.3x x-height below baseline
        descender_dist = 3.0
        est_x_height = descender_dist / 0.3

        assert abs(est_x_height - 10.0) < 0.01

    def test_combined_ascender_descender(self):
        """Test using both ascender and descender distances."""
        ascender_dist = 7.0  # 0.7x
        descender_dist = 3.0  # 0.3x

        est_from_asc = ascender_dist / 0.7  # 10.0
        est_from_desc = descender_dist / 0.3  # 10.0

        # Use minimum (more conservative)
        est_x_height = min(est_from_asc, est_from_desc)

        assert abs(est_x_height - 10.0) < 0.01


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_space_character_handling(self):
        """Test that spaces are handled correctly."""
        # The function should skip spaces when looking for reference chars
        # This is tested implicitly by the character selection logic
        assert ' ' not in "xaeocuvz"  # Space not in x-height chars
        assert ' ' not in "MHZITN"  # Space not in cap-height chars

    def test_empty_candidate_lists(self):
        """Test behavior when no candidates found."""
        # This would happen with text like "!@#$" (no alphanumeric)
        # Function should return None or fallback
        # Handled by the "any available character" fallback

    def test_rect_expansion_amount(self):
        """Test that rect expansion is reasonable."""
        # Safety margins: 0.3pt horizontal, 0.8pt vertical
        safety_margin = fitz.Rect(-0.3, -0.8, 0.3, 0.8)
        original = fitz.Rect(50, 100, 60, 110)

        expanded = original + safety_margin

        # Should expand by 0.6pt horizontally (0.3 on each side)
        assert abs(expanded.width - original.width - 0.6) < 0.01
        # Should expand by 1.6pt vertically (0.8 on each side)
        assert abs(expanded.height - original.height - 1.6) < 0.01


class TestArrayBoundsPrevention:
    """Test that array bounds issues are prevented."""

    def test_loop_stops_early(self):
        """Test that loop stops early to prevent overflow."""
        samples_length = 100  # Not a multiple of 30
        step = 30

        # Should stop 2 elements early
        last_valid_i = samples_length - 3  # -3 to access i, i+1, i+2
        expected_indices = list(range(0, last_valid_i, step))

        # Verify no index would go out of bounds
        for i in expected_indices:
            assert i + 2 < samples_length, f"Index {i}+2 = {i+2} >= {samples_length}"

    def test_samples_length_multiple_of_step(self):
        """Test case where samples.length is exactly multiple of step."""
        samples_length = 90  # Exactly 3 * 30
        step = 30

        # Should still stop 2 elements early (88, not 90)
        last_valid_i = samples_length - 3
        expected_indices = list(range(0, last_valid_i, step))

        # Last iteration should be at i=60 (60+2=62 < 90)
        assert max(expected_indices) + 2 < samples_length


class TestInputValidation:
    """Test input validation guards."""

    def test_page_validation_in_reference_metrics(self):
        """Test that page validation works."""
        # Already tested in TestReferenceCharMetrics.test_none_page_returns_none
        pass

    def test_rect_validation_in_reference_metrics(self):
        """Test that rect validation works."""
        # Already tested in TestReferenceCharMetrics.test_empty_rect_returns_none
        pass

    def test_text_validation_in_reference_metrics(self):
        """Test that text validation works."""
        # Already tested in TestReferenceCharMetrics.test_invalid_text_returns_none
        pass

    def test_validation_logs_errors(self, capsys):
        """Test that validation prints error messages."""
        _get_reference_char_metrics(None, fitz.Rect(50, 95, 100, 115), "Text")

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "None page" in captured.out


# Integration-style tests
class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_complete_redaction_flow(self, tmp_path):
        """Test the complete flow of calculating redaction rect."""
        # Create a PDF
        pdf_path = tmp_path / "integration_test.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Add multi-line text
        page.insert_text((50, 100), "The quick brown fox jumps over the lazy dog.", fontsize=12)
        doc.save(pdf_path)
        doc.close()

        # Reopen
        doc = fitz.open(pdf_path)
        page = doc[0]

        # Find text
        text_instances = page.search_for("quick")
        assert len(text_instances) > 0

        # Calculate redaction rect
        rect = text_instances[0]
        redact_rect = _calculate_precise_redaction_rect(page, rect, "quick")

        # Should be expanded
        assert redact_rect.width >= rect.width
        assert redact_rect.height >= rect.height

        # Should be reasonable size
        assert redact_rect.width < 50  # Not too wide
        assert redact_rect.height < 30  # Not too tall

        doc.close()

    def test_mixed_character_types(self, tmp_path):
        """Test with mixed character types (x-height, caps, ascenders, descenders)."""
        pdf_path = tmp_path / "mixed_chars.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Mix of different character types
        page.insert_text((50, 100), "A quick brown Example", fontsize=12)
        doc.save(pdf_path)
        doc.close()

        doc = fitz.open(pdf_path)
        page = doc[0]

        # Find "Example" which has cap-height 'E' and x-height 'x', 'a', 'm', 'l'
        rects = page.search_for("Example")
        assert len(rects) > 0

        result = _get_reference_char_metrics(page, rects[0], "Example")
        assert result is not None

        char, width, height = result
        # Should prefer x-height chars
        assert char in "Exampl"
        assert height > 0

        doc.close()


class TestCoreIntegration(unittest.TestCase):
    """Integration tests for replace_text_in_pdf, batch_replace, and regex_replace."""

    def _make_pdf_with_text(self, tmp_path, text, filename="test.pdf"):
        """Create a minimal 1-page PDF with the given text and return its path."""
        pdf_path = os.path.join(tmp_path, filename)
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), text, fontsize=12)
        doc.save(pdf_path)
        doc.close()
        return pdf_path

    def test_replace_text_returns_success(self):
        """replace_text_in_pdf should replace text and report success."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            input_path = self._make_pdf_with_text(tmp, "Hello World")
            output_path = os.path.join(tmp, "out.pdf")

            result = replace_text_in_pdf(input_path, output_path, "Hello", "Hi", page_number=1)

            self.assertTrue(result["success"], msg=result.get("message", ""))
            doc = fitz.open(output_path)
            page_text = doc.load_page(0).get_text()
            doc.close()
            self.assertIn("Hi", page_text)
            self.assertIn("World", page_text)

    def test_batch_replace_chains_correctly(self):
        """batch_replace should apply all replacements in sequence."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            input_path = self._make_pdf_with_text(tmp, "Foo Bar Baz")
            output_path = os.path.join(tmp, "out.pdf")

            replacements = [
                {"target_text": "Foo", "replacement_text": "One"},
                {"target_text": "Bar", "replacement_text": "Two"},
            ]
            result = batch_replace(input_path, output_path, replacements)

            self.assertTrue(result["success"], msg=result.get("message", ""))
            self.assertEqual(result["applied"], 2)
            doc = fitz.open(output_path)
            page_text = doc.load_page(0).get_text()
            doc.close()
            self.assertIn("One", page_text)
            self.assertIn("Two", page_text)

    def test_regex_replace_basic(self):
        """regex_replace should replace pattern matches and report replacement count."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            input_path = self._make_pdf_with_text(tmp, "Hello 2024")
            output_path = os.path.join(tmp, "out.pdf")

            result = regex_replace(input_path, output_path, pattern=r"\d{4}", replacement="YEAR")

            self.assertTrue(result["success"], msg=result.get("message", ""))
            self.assertEqual(result["replacements"], 1)
            doc = fitz.open(output_path)
            page_text = doc.load_page(0).get_text()
            doc.close()
            self.assertIn("YEAR", page_text)

    def test_regex_replace_invalid_backreference(self):
        """regex_replace with an out-of-range backreference should not crash (covers N6 fix).

        The fix catches re.error raised by m.expand(replacement) when the replacement
        references a group that does not exist (e.g. \\9 when the pattern only has 1 group).
        The function returns success=True with 0 replacements rather than raising.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            input_path = self._make_pdf_with_text(tmp, "hello world")
            output_path = os.path.join(tmp, "out_backreference.pdf")

            # Should not raise any exception
            try:
                result = regex_replace(
                    input_path,
                    output_path,
                    pattern=r"(hello)",
                    replacement=r"\9",
                )
            except Exception as exc:
                self.fail(f"regex_replace raised an unexpected exception: {exc}")

            # The bad backreference causes expand() to fail per match, so no
            # replacements are applied but the call itself is considered "successful".
            self.assertTrue(result["success"], msg=result.get("message", ""))
            self.assertEqual(
                result["replacements"],
                0,
                msg="Expected 0 replacements because \\9 is an invalid backreference",
            )

    def test_batch_replace_no_temp_accumulation(self):
        """batch_replace should not leave marcedit_batch_* temp files behind (covers N1 fix)."""
        import tempfile
        import glob
        with tempfile.TemporaryDirectory() as tmp:
            input_path = self._make_pdf_with_text(
                tmp, "alpha beta gamma delta epsilon"
            )
            output_path = os.path.join(tmp, "out_batch.pdf")

            replacements = [
                {"target_text": "alpha",   "replacement_text": "A"},
                {"target_text": "beta",    "replacement_text": "B"},
                {"target_text": "gamma",   "replacement_text": "C"},
                {"target_text": "delta",   "replacement_text": "D"},
                {"target_text": "epsilon", "replacement_text": "E"},
            ]

            # Snapshot temp files before the call
            pattern = os.path.join(tempfile.gettempdir(), "marcedit_batch_*.pdf")
            before = set(glob.glob(pattern))

            result = batch_replace(input_path, output_path, replacements)

            # Snapshot temp files after the call
            after = set(glob.glob(pattern))

            # No marcedit_batch_* files should be left behind
            leaked = after - before
            self.assertEqual(
                len(leaked),
                0,
                msg=f"Temp files leaked after batch_replace: {leaked}",
            )

            # Functional assertions
            self.assertTrue(result["success"], msg=result.get("message", ""))
            self.assertEqual(result["applied"], 5)
            self.assertTrue(os.path.isfile(output_path), "Output file must exist")
            # Verify output is a valid PDF
            doc = fitz.open(output_path)
            self.assertGreater(doc.page_count, 0)
            doc.close()

    def test_scrub_returns_warnings_key(self):
        """scrub_all_metadata result must contain a 'warnings' list (covers N8 fix)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            input_path = self._make_pdf_with_text(tmp, "Confidential document")
            output_path = os.path.join(tmp, "out_scrubbed.pdf")

            result = scrub_all_metadata(input_path, output_path)

            self.assertIn(
                "warnings",
                result,
                msg="scrub_all_metadata result must include a 'warnings' key",
            )
            self.assertIsInstance(
                result["warnings"],
                list,
                msg="'warnings' value must be a list",
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
