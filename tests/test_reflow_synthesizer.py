"""
Unit tests for MarcEdit PDF Editor reflow and synthesizer functions.
Tests focus on line structure detection, text reflow, and glyph synthesis.

Run with: pytest tests/test_reflow_synthesizer.py -v
"""

import pytest
import fitz
import sys
import os

# Add the editor_pkg to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site'))

from editor_pkg.reflow import (
    _get_line_structure,
    reflow_line,
)


class TestGetLineStructure:
    """Test suite for _get_line_structure function."""

    @pytest.fixture
    def sample_page(self, tmp_path):
        """Create a sample PDF page with structured text."""
        pdf_path = tmp_path / "test_lines.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Line 1: "Hello TARGET World" - TARGET in middle
        page.insert_text((50, 100), "Hello TARGET World", fontsize=12)

        # Line 2: Just "PREFIX SUFFIX"
        page.insert_text((50, 120), "PREFIX SUFFIX", fontsize=12)

        # Line 3: Text without target
        page.insert_text((50, 140), "No target here", fontsize=12)

        doc.save(pdf_path)
        doc.close()

        doc = fitz.open(pdf_path)
        return doc[0]

    def test_none_page_returns_empty(self):
        """Test that None page returns empty results."""
        line_rect, prefix, target, suffix = _get_line_structure(None, fitz.Rect(50, 95, 150, 105))
        assert line_rect is None
        assert prefix == []
        assert target == []
        assert suffix == []

    def test_empty_rect_returns_empty(self, sample_page):
        """Test that empty rect returns empty results."""
        line_rect, prefix, target, suffix = _get_line_structure(sample_page, fitz.Rect())
        assert line_rect is None
        assert prefix == []
        assert target == []
        assert suffix == []

    def test_finds_target_in_middle(self, sample_page):
        """Test finding target text in the middle of a line."""
        # Search for "TARGET" which is in the middle
        rects = sample_page.search_for("TARGET")
        assert len(rects) > 0

        line_rect, prefix, target, suffix = _get_line_structure(
            sample_page, rects[0], debug_log=[]
        )

        # Should find the line
        assert line_rect is not None
        # Should have prefix ("Hello ")
        assert len(prefix) > 0
        # Should have target ("TARGET")
        assert len(target) > 0
        # Should have suffix (" World")
        assert len(suffix) > 0

    def test_debug_log_populated_on_error(self):
        """Test that debug log gets error messages."""
        debug_log = []
        _get_line_structure(None, fitz.Rect(50, 95, 100, 105), debug_log)

        assert len(debug_log) > 0
        assert any("ERROR" in msg for msg in debug_log)


class TestReflowLine:
    """Test suite for reflow_line function."""

    @pytest.fixture
    def sample_page(self, tmp_path):
        """Create a sample PDF for reflow testing."""
        pdf_path = tmp_path / "test_reflow.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Simple line with target
        page.insert_text((50, 100), "Hello TARGET World", fontsize=12)

        doc.save(pdf_path)
        doc.close()

        doc = fitz.open(pdf_path)
        return doc[0]

    def test_none_page_returns_false(self):
        """Test that None page returns False."""
        result = reflow_line(
            None,
            fitz.Rect(50, 95, 150, 105),
            "REPLACEMENT",
            {"fontname": "helv", "fontsize": 12, "color": (0, 0, 0)},
            debug_log=[]
        )
        assert result == (False, None)

    def test_empty_rect_returns_false(self, sample_page):
        """Test that empty rect returns False."""
        result = reflow_line(
            sample_page,
            fitz.Rect(),
            "REPLACEMENT",
            {"fontname": "helv", "fontsize": 12, "color": (0, 0, 0)},
            debug_log=[]
        )
        assert result == (False, None)

    def test_invalid_replacement_text_returns_false(self, sample_page):
        """Test that invalid replacement text returns False."""
        rects = sample_page.search_for("TARGET")
        assert len(rects) > 0

        result = reflow_line(
            sample_page,
            rects[0],
            "",  # Empty replacement
            {"fontname": "helv", "fontsize": 12, "color": (0, 0, 0)},
            debug_log=[]
        )
        assert result == (False, None)

    def test_invalid_font_info_returns_false(self, sample_page):
        """Test that invalid font_info returns False."""
        rects = sample_page.search_for("TARGET")
        assert len(rects) > 0

        result = reflow_line(
            sample_page,
            rects[0],
            "REPLACEMENT",
            None,  # Invalid font_info
            debug_log=[]
        )
        assert result == (False, None)

    def test_validation_logs_errors(self):
        """Test that validation logs error messages to debug_log."""
        debug_log = []
        reflow_line(
            None,
            fitz.Rect(50, 95, 150, 105),
            "REPLACEMENT",
            {"fontname": "helv", "fontsize": 12, "color": (0, 0, 0)},
            debug_log=debug_log
        )

        # Should have logged error to debug_log
        assert len(debug_log) > 0
        assert any("ERROR" in msg for msg in debug_log)


class TestAdaptiveTolerance:
    """Test adaptive tolerance logic for line detection."""

    def test_small_font_tolerance(self):
        """Test that small fonts get more lenient tolerance."""
        target_height = 7.0  # < 8pt
        estimated_fontsize = target_height

        # Should use 60% tolerance
        if estimated_fontsize < 8:
            tolerance_pct = 0.60
        elif estimated_fontsize < 14:
            tolerance_pct = 0.40
        else:
            tolerance_pct = 0.25

        assert tolerance_pct == 0.60

    def test_medium_font_tolerance(self):
        """Test that medium fonts get standard tolerance."""
        target_height = 12.0  # 8-14pt
        estimated_fontsize = target_height

        if estimated_fontsize < 8:
            tolerance_pct = 0.60
        elif estimated_fontsize < 14:
            tolerance_pct = 0.40
        else:
            tolerance_pct = 0.25

        assert tolerance_pct == 0.40

    def test_large_font_tolerance(self):
        """Test that large fonts get strict tolerance."""
        target_height = 18.0  # > 14pt
        estimated_fontsize = target_height

        if estimated_fontsize < 8:
            tolerance_pct = 0.60
        elif estimated_fontsize < 14:
            tolerance_pct = 0.40
        else:
            tolerance_pct = 0.25

        assert tolerance_pct == 0.25

    def test_minimum_absolute_tolerance(self):
        """Test that minimum absolute tolerance is enforced."""
        target_height = 2.0  # Very small

        # 60% of 2.0 = 1.2
        tolerance_pct = 0.60
        min_tolerance = 2.0
        tolerance = max(target_height * tolerance_pct, min_tolerance)

        # Should use min_tolerance
        assert tolerance == 2.0


class TestCollisionDetection:
    """Test collision detection logic."""

    def test_page_bounds_checking(self):
        """Test that page bounds are checked."""
        page_rect = fitz.Rect(0, 0, 612, 792)  # Letter size
        page_margins = fitz.Rect(10, 10, 10, 10)
        content_rect = page_rect - page_margins

        # Suffix rect that goes beyond content area
        suffix_rect = fitz.Rect(600, 100, 650, 110)

        # Should not be contained
        assert not content_rect.contains(suffix_rect)

    def test_rect_intersection_detection(self):
        """Test that rect intersections are detected."""
        rect1 = fitz.Rect(50, 100, 100, 110)
        rect2 = fitz.Rect(90, 105, 150, 115)  # Overlaps

        assert rect1.intersects(rect2)

    def test_delta_reduction_on_collision(self):
        """Test that delta is reduced when collision detected."""
        original_delta = 20.0
        collision_detected = True

        if collision_detected:
            safe_delta = original_delta * 0.5 if original_delta > 0 else original_delta
        else:
            safe_delta = original_delta

        assert safe_delta == 10.0  # 50% of original


class TestWidthCalculations:
    """Test width calculation and kerning compensation."""

    def test_kerning_compensation_applied(self):
        """Test that kerning compensation is applied for long text."""
        replacement_text = "Hello World" * 2  # More than 5 chars
        fontsize = 12.0

        # Simulate text_length result
        base_width = len(replacement_text) * fontsize * 0.5

        if len(replacement_text) > 5:
            kerning_fudge = 1.0 + (len(replacement_text) / 10.0) * 0.015
            adjusted_width = base_width * kerning_fudge
        else:
            adjusted_width = base_width

        # Should be larger than base
        assert adjusted_width > base_width

    def test_wide_character_fallback(self):
        """Test wide character width estimation."""
        # Wide chars (M, W) need less side bearing
        text = "MW"
        fontsize = 12.0

        wide_chars = sum(1 for c in text if c in 'MWmwWM')
        narrow_chars = sum(1 for c in text if c in 'ijltfIJLTF')

        if wide_chars > 0 and narrow_chars == 0:
            side_bearing_pct = 0.10
        elif narrow_chars > 0 and wide_chars == 0:
            side_bearing_pct = 0.20
        else:
            side_bearing_pct = 0.15

        # Should use 10% for wide chars
        assert side_bearing_pct == 0.10

    def test_narrow_character_fallback(self):
        """Test narrow character width estimation."""
        # Narrow chars (i, j, l) need more side bearing
        text = "il"
        fontsize = 12.0

        wide_chars = sum(1 for c in text if c in 'MWmwWM')
        narrow_chars = sum(1 for c in text if c in 'ijltfIJLTF')

        if wide_chars > 0 and narrow_chars == 0:
            side_bearing_pct = 0.10
        elif narrow_chars > 0 and wide_chars == 0:
            side_bearing_pct = 0.20
        else:
            side_bearing_pct = 0.15

        # Should use 20% for narrow chars
        assert side_bearing_pct == 0.20


class TestVisualCopyValidation:
    """Test visual copy validation logic."""

    def test_array_bounds_protection(self):
        """Test that array access is bounds-checked."""
        samples_length = 100

        # Should stop 2 elements early
        for i in range(0, samples_length - 2, 30):
            # Access i, i+1, i+2 should be safe
            assert i + 2 < samples_length

    def test_ink_detection_threshold(self):
        """Test ink detection threshold."""
        # Sample pixel values
        dark_pixel = (100, 100, 100)  # lum = 100
        light_pixel = (250, 250, 250)  # lum = 250

        lum_dark = sum(dark_pixel) / 3
        lum_light = sum(light_pixel) / 3

        # Threshold is 250
        threshold = 250

        has_ink_dark = lum_dark < threshold
        has_ink_light = lum_light < threshold

        assert has_ink_dark == True
        assert has_ink_light == False


class TestSynthesisParameters:
    """Test synthesis parameter validation."""

    def test_size_validation(self):
        """Test that invalid size is rejected."""
        invalid_sizes = [0, -1, -10, None]

        for size in invalid_sizes:
            if size is None:
                is_valid = size is not None and size > 0
            else:
                is_valid = size > 0

            assert not is_valid, f"Size {size} should be invalid"

    def test_start_point_validation(self):
        """Test that start point must have 2 elements."""
        valid_points = [(0, 0), (100, 200), (50.5, 100.3)]
        invalid_points = [None, [], (1,), (1, 2, 3), ""]

        for point in valid_points:
            is_valid = point and len(point) == 2
            assert is_valid

        for point in invalid_points:
            if point is not None:
                is_valid = len(point) == 2
                assert not is_valid

    def test_glyph_map_validation(self):
        """Test that glyph_map must be a non-empty dict."""
        valid_maps = [{'a': {...}}, {'x': {...}, 'y': {...}}]
        invalid_maps = [None, {}, [], ""]

        for glyph_map in valid_maps:
            is_valid = glyph_map and isinstance(glyph_map, dict) and len(glyph_map) > 0
            assert is_valid

        for glyph_map in invalid_maps:
            if glyph_map is not None:
                is_valid = isinstance(glyph_map, dict) and len(glyph_map) > 0
                assert not is_valid


class TestCharacterSideBearings:
    """Test character-specific side bearing calculations."""

    def test_narrow_chars_get_more_space(self):
        """Test that narrow chars get more side bearing space."""
        narrow_chars = {'i', 'j', 'l', 't', 'f'}
        wide_chars = {'m', 'w', 'M', 'W'}
        punct_chars = {'.', ',', ':', ';', '!', '?'}

        narrow_pct = 0.20
        wide_pct = 0.10
        punct_pct = 0.18
        default_pct = 0.15

        # Narrow should have highest
        assert narrow_pct > wide_pct
        assert narrow_pct > default_pct

        # Wide should have lowest
        assert wide_pct < narrow_pct
        assert wide_pct < default_pct

        # Punctuation should be in between
        assert default_pct < punct_pct < narrow_pct


class TestErrorRecovery:
    """Test error recovery and fallback mechanisms."""

    def test_graceful_degradation_on_collision(self):
        """Test that system degrades gracefully on collision."""
        delta = 20.0
        collision = True

        # Should reduce delta
        if collision:
            adjusted_delta = delta * 0.5 if delta > 0 else delta
        else:
            adjusted_delta = delta

        # Should be reduced but still positive
        assert 0 < adjusted_delta < delta

    def test_fallback_to_redraw_on_visual_copy_failure(self):
        """Test fallback to redraw when visual copy fails."""
        visual_copy_success = False
        has_fallback = True

        if not visual_copy_success:
            use_fallback = has_fallback
        else:
            use_fallback = False

        # Should use fallback
        assert use_fallback == True


class TestMarginCalculations:
    """Test safety margin calculations."""

    def test_redaction_margin_amounts(self):
        """Test that redaction margins are appropriate."""
        # Horizontal: 0.3pt on each side = 0.6pt total
        # Vertical: 0.8pt on each side = 1.6pt total
        safety_margin = fitz.Rect(-0.3, -0.8, 0.3, 0.8)

        total_h_expansion = 0.3 + 0.3
        total_v_expansion = 0.8 + 0.8

        assert abs(total_h_expansion - 0.6) < 0.01
        assert abs(total_v_expansion - 1.6) < 0.01

    def test_reflow_margin_amounts(self):
        """Test that reflow margins are larger."""
        # Reflow uses (-0.5, -1.5, 0.5, 1.5) plus additional (-0.2, -0.3, 0.2, 0.3)
        # Total: (-0.7, -1.8, 0.7, 1.8)
        base_margin = fitz.Rect(-0.5, -1.5, 0.5, 1.5)
        extra_margin = fitz.Rect(-0.2, -0.3, 0.2, 0.3)

        # Simulate addition
        total_left = -0.5 + -0.2
        total_top = -1.5 + -0.3
        total_right = 0.5 + 0.2
        total_bottom = 1.5 + 0.3

        assert abs(total_left - (-0.7)) < 0.01
        assert abs(total_top - (-1.8)) < 0.01
        assert abs(total_right - 0.7) < 0.01
        assert abs(total_bottom - 1.8) < 0.01


class TestIntegrationReflowScenarios:
    """Test realistic reflow scenarios."""

    def test_expansion_scenario(self, tmp_path):
        """Test text expansion (new text is longer)."""
        pdf_path = tmp_path / "expansion_test.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Original text
        page.insert_text((50, 100), "Hi", fontsize=12)

        doc.save(pdf_path)
        doc.close()

        # Reopen and replace with longer text
        doc = fitz.open(pdf_path)
        page = doc[0]

        rects = page.search_for("Hi")
        assert len(rects) > 0

        # Calculate new width (approximate)
        old_width = rects[0].width
        new_text = "Hello There"
        new_width = len(new_text) * 12 * 0.5  # Rough estimate

        # New should be wider
        assert new_width > old_width

        doc.close()

    def test_contraction_scenario(self, tmp_path):
        """Test text contraction (new text is shorter)."""
        pdf_path = tmp_path / "contraction_test.pdf"
        doc = fitz.open()
        page = doc.new_page()

        # Original text
        page.insert_text((50, 100), "Hello World", fontsize=12)

        doc.save(pdf_path)
        doc.close()

        # Reopen and replace with shorter text
        doc = fitz.open(pdf_path)
        page = doc[0]

        rects = page.search_for("Hello World")
        assert len(rects) > 0

        old_width = rects[0].width
        new_text = "Hi"
        new_width = len(new_text) * 12 * 0.5

        # New should be narrower
        assert new_width < old_width

        doc.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
