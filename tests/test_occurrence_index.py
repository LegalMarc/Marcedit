"""
Regression test for issue #29: Edit only the clicked occurrence, not every match.

The Python backend (`replace_text_in_pdf`) already accepts
`manual_overrides={'occurrence_index': N}` to replace only the Nth
(0-based) occurrence on a page.  This test verifies:

  1. occurrence_index=1 replaces ONLY the 2nd instance; the 1st and 3rd
     are unchanged.
  2. With no occurrence_index key (back-compat), ALL instances are replaced.

Run with:
    pytest tests/test_occurrence_index.py -q
"""

import os
import sys
import tempfile
import unittest

import fitz  # PyMuPDF

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SITE = os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site")
if _SITE not in sys.path:
    sys.path.insert(0, _SITE)

from editor_pkg.core import replace_text_in_pdf  # noqa: E402


def _build_triple_pdf(path: str, token: str = "ALPHA") -> None:
    """Build a single-page PDF with `token` appearing exactly 3 times."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Place the token three times on the same line, well separated.
    page.insert_text((72, 200), f"{token}   {token}   {token}", fontsize=14)
    doc.save(path)
    doc.close()


def _extract_page_text(path: str, page_number: int = 1) -> str:
    """Return all text on `page_number` (1-based) as a single string."""
    doc = fitz.open(path)
    page = doc[page_number - 1]
    text = page.get_text("text")
    doc.close()
    return text


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


class TestOccurrenceIndexTargeting(unittest.TestCase):
    """replace_text_in_pdf must honour manual_overrides['occurrence_index']."""

    def setUp(self):
        fd, self.src = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        fd, self.dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        _build_triple_pdf(self.src, token="ALPHA")

    def tearDown(self):
        _cleanup(self.src, self.dst)

    # ── targeted replacement ────────────────────────────────────────────────

    def test_occurrence_index_1_replaces_only_second_instance(self):
        """occurrence_index=1 must change only the 2nd ALPHA; 1st and 3rd intact."""
        result = replace_text_in_pdf(
            input_path=self.src,
            output_path=self.dst,
            target_text="ALPHA",
            replacement_text="BETA",
            page_number=1,
            manual_overrides={"occurrence_index": 1},
        )
        self.assertTrue(result["success"], f"Replacement failed: {result.get('message')}")

        text = _extract_page_text(self.dst)
        # Exactly one BETA must appear.
        self.assertEqual(text.count("BETA"), 1,
                         f"Expected 1 BETA, got {text.count('BETA')}. Page text: {text!r}")
        # Two ALPHAs must remain (the 1st and 3rd).
        self.assertEqual(text.count("ALPHA"), 2,
                         f"Expected 2 ALPHA remaining, got {text.count('ALPHA')}. Page text: {text!r}")

    def test_occurrence_index_0_replaces_only_first_instance(self):
        """occurrence_index=0 must change only the 1st ALPHA."""
        result = replace_text_in_pdf(
            input_path=self.src,
            output_path=self.dst,
            target_text="ALPHA",
            replacement_text="GAMMA",
            page_number=1,
            manual_overrides={"occurrence_index": 0},
        )
        self.assertTrue(result["success"], f"Replacement failed: {result.get('message')}")

        text = _extract_page_text(self.dst)
        self.assertEqual(text.count("GAMMA"), 1,
                         f"Expected 1 GAMMA, got {text.count('GAMMA')}. Page text: {text!r}")
        self.assertEqual(text.count("ALPHA"), 2,
                         f"Expected 2 ALPHA remaining, got {text.count('ALPHA')}. Page text: {text!r}")

    # ── back-compat: no occurrence_index ───────────────────────────────────

    def test_no_occurrence_index_replaces_all_instances(self):
        """Without occurrence_index, ALL three ALPHAs must be replaced."""
        result = replace_text_in_pdf(
            input_path=self.src,
            output_path=self.dst,
            target_text="ALPHA",
            replacement_text="DELTA",
            page_number=1,
            manual_overrides={},   # no occurrence_index key
        )
        self.assertTrue(result["success"], f"Replacement failed: {result.get('message')}")

        text = _extract_page_text(self.dst)
        self.assertEqual(text.count("ALPHA"), 0,
                         f"Expected 0 ALPHA remaining, got {text.count('ALPHA')}. Page text: {text!r}")
        self.assertEqual(text.count("DELTA"), 3,
                         f"Expected 3 DELTA, got {text.count('DELTA')}. Page text: {text!r}")

    def test_no_overrides_at_all_replaces_all_instances(self):
        """With manual_overrides=None (omitted), ALL occurrences are replaced."""
        result = replace_text_in_pdf(
            input_path=self.src,
            output_path=self.dst,
            target_text="ALPHA",
            replacement_text="EPSILON",
            page_number=1,
            manual_overrides=None,
        )
        self.assertTrue(result["success"], f"Replacement failed: {result.get('message')}")

        text = _extract_page_text(self.dst)
        self.assertEqual(text.count("ALPHA"), 0,
                         f"Expected 0 ALPHA remaining, got {text.count('ALPHA')}. Page text: {text!r}")


if __name__ == "__main__":
    unittest.main()
