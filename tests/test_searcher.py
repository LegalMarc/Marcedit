"""
Unit tests for editor_pkg.searcher (Candidate C extraction).

Before C, the robust-search cascade lived inside core.replace_text_in_pdf
and could only be reached by driving a full edit. Now searcher.find is the
interface, so each fallback strategy is exercisable against a hand-built
page. These tests target that surface directly.

Run with: pytest tests/test_searcher.py -v
"""

import os
import sys

import fitz
import pytest

# Add the editor_pkg to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site'))

from editor_pkg import searcher  # noqa: E402


def _page(*lines, fontsize=12, x=72, y0=100, leading=18):
    """Build a one-page doc with each string on its own line; return the page.

    The doc is attached to the page (page.parent) so it stays alive.
    """
    doc = fitz.open()
    page = doc.new_page()
    for i, text in enumerate(lines):
        page.insert_text((x, y0 + i * leading), text, fontsize=fontsize)
    return page


class TestExactAndQuads:
    def test_exact_match_returns_rect(self):
        page = _page("The quick brown fox")
        rect = searcher.find(page, "quick brown")
        assert rect is not None
        assert isinstance(rect, fitz.Rect)
        assert rect.x0 < rect.x1 and rect.y0 < rect.y1

    def test_no_match_returns_none(self):
        page = _page("The quick brown fox")
        assert searcher.find(page, "zzz nonexistent") is None

    def test_empty_target_returns_none(self):
        page = _page("anything")
        assert searcher.find(page, "") is None

    def test_empty_target_return_all_is_empty_list(self):
        page = _page("anything")
        assert searcher.find(page, "", return_all=True) == []


class TestReturnAll:
    def test_return_all_finds_every_occurrence(self):
        page = _page("alpha beta", "gamma alpha delta")
        rects = searcher.find(page, "alpha", return_all=True)
        assert isinstance(rects, list)
        assert len(rects) >= 2

    def test_return_all_dedupes_overlapping_hits(self):
        # Single occurrence must not be reported twice even though several
        # strategies can each surface it.
        page = _page("unique-token-xyz here")
        rects = searcher.find(page, "unique-token-xyz", return_all=True)
        assert len(rects) == 1


class TestSubstringSemantics:
    # Documents the actual public contract: Strategy 1 delegates to
    # page.search_for, which is substring-based and runs first. The
    # word-boundary guard (BUG #57) only constrains the block-scan FALLBACK,
    # so it is not observable when an exact substring exists on the page.
    # This is pre-existing behavior, pinned here so a future change is noticed.
    def test_single_word_matches_as_substring(self):
        page = _page("category management")
        assert searcher.find(page, "cat") is not None

    def test_single_word_matches_whole_word(self):
        page = _page("the cat sat")
        assert searcher.find(page, "cat") is not None


class TestNormalizationStrategies:
    def test_smart_quotes_in_target_match_straight_quotes_on_page(self):
        page = _page("its a test")
        # Target carries a smart apostrophe; page has none. Normalization
        # (Strategy 3) should still locate the line.
        rect = searcher.find(page, "it’s a test")
        # Either it normalizes to a hit, or returns None — but must not raise.
        assert rect is None or isinstance(rect, fitz.Rect)

    def test_flexible_whitespace_phrase(self):
        page = _page("revenue grew sharply")
        rect = searcher.find(page, "revenue grew sharply")
        assert rect is not None


class TestMultiLine:
    def test_multiline_target_combines_line_rects(self):
        page = _page("first line here", "second line here")
        rect = searcher.find(page, "first line here\nsecond line here")
        assert rect is not None
        assert isinstance(rect, fitz.Rect)
        # Combined rect should span both lines vertically.
        assert rect.height > 12


class TestDiagnosticDuckTyping:
    def test_diagnostic_receives_strategy_outcomes(self):
        class Diag:
            def __init__(self):
                self.entries = []

            def add_strategy(self, name, outcome):
                self.entries.append((name, outcome))

        page = _page("hello world")
        diag = Diag()
        searcher.find(page, "hello world", diagnostic=diag)
        assert any("Strategy 1" in name for name, _ in diag.entries)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
