"""
Regression test for issue #30: font-unavailable should fail cleanly, not silently
substitute Helvetica.

When reflow.reflow_line() returns (False, "font_unavailable") — the BUG-4
sentinel — and the caller sets manual_overrides={'fail_on_font_unavailable': True},
_apply_replace_to_open_doc must surface success=False instead of inserting
Helvetica/Times as a wrong-font substitute.

Back-compat: without the flag (default), the legacy Helvetica insertion path
is still taken (success=True), preserving existing behavior.

Run with:
    pytest tests/test_font_unavailable.py -q
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import fitz  # PyMuPDF

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SITE = os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site")
if _SITE not in sys.path:
    sys.path.insert(0, _SITE)

from editor_pkg.core import _apply_replace_to_open_doc  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_simple_pdf(path: str, token: str = "HELLO") -> None:
    """Build a single-page PDF containing one instance of token."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 200), token, fontsize=14)
    doc.save(path)
    doc.close()


def _extract_page_text(doc: fitz.Document, page_number: int = 1) -> str:
    """Return all text on page_number (1-based)."""
    page = doc[page_number - 1]
    return page.get_text("text")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFontUnavailableFailClean(unittest.TestCase):
    """
    _apply_replace_to_open_doc must respect the fail_on_font_unavailable flag.
    """

    def setUp(self):
        fd, self.src = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        _build_simple_pdf(self.src, token="HELLO")
        self.doc = fitz.open(self.src)

    def tearDown(self):
        self.doc.close()
        try:
            os.unlink(self.src)
        except OSError:
            pass

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _reflow_returns_font_unavailable(page, rect, replacement_text,
                                         font_info, debug_log=None,
                                         font_buffer=None):
        """Stub that simulates the BUG-4 font-unavailable sentinel."""
        if debug_log is not None:
            debug_log.append("Reflow: Simulated font_unavailable sentinel")
        return False, "font_unavailable"

    # -- tests -----------------------------------------------------------

    def test_fail_on_font_unavailable_flag_surfaces_failure(self):
        """
        With fail_on_font_unavailable=True, the edit must return success=False
        rather than silently insert Helvetica.
        """
        with patch("editor_pkg.core.reflow.reflow_line",
                   side_effect=self._reflow_returns_font_unavailable):
            result = _apply_replace_to_open_doc(
                self.doc,
                target_text="HELLO",
                replacement_text="WORLD",
                page_number=1,
                manual_overrides={"fail_on_font_unavailable": True},
            )

        self.assertFalse(
            result["success"],
            f"Expected success=False when font_unavailable; got: {result}",
        )
        self.assertEqual(
            result.get("message"), "font_unavailable",
            f"Expected message='font_unavailable'; got: {result.get('message')!r}",
        )

    def test_without_flag_falls_back_to_helv_and_succeeds(self):
        """
        Without the flag (default back-compat), font-unavailable must still
        fall through to the legacy Helvetica insertion and return success=True.
        """
        with patch("editor_pkg.core.reflow.reflow_line",
                   side_effect=self._reflow_returns_font_unavailable):
            result = _apply_replace_to_open_doc(
                self.doc,
                target_text="HELLO",
                replacement_text="WORLD",
                page_number=1,
                manual_overrides={},   # no fail_on_font_unavailable key
            )

        self.assertTrue(
            result["success"],
            f"Expected success=True for back-compat (no flag); got: {result}",
        )

    def test_flag_false_also_falls_back(self):
        """
        Explicit fail_on_font_unavailable=False must also use legacy path.
        """
        with patch("editor_pkg.core.reflow.reflow_line",
                   side_effect=self._reflow_returns_font_unavailable):
            result = _apply_replace_to_open_doc(
                self.doc,
                target_text="HELLO",
                replacement_text="WORLD",
                page_number=1,
                manual_overrides={"fail_on_font_unavailable": False},
            )

        self.assertTrue(
            result["success"],
            f"Expected success=True when flag is False; got: {result}",
        )

    def test_no_overrides_at_all_falls_back(self):
        """
        With manual_overrides=None, must use legacy path (back-compat).
        """
        with patch("editor_pkg.core.reflow.reflow_line",
                   side_effect=self._reflow_returns_font_unavailable):
            result = _apply_replace_to_open_doc(
                self.doc,
                target_text="HELLO",
                replacement_text="WORLD",
                page_number=1,
                manual_overrides=None,
            )

        self.assertTrue(
            result["success"],
            f"Expected success=True when manual_overrides=None; got: {result}",
        )

    def test_reflow_success_unaffected(self):
        """
        Normal (non-font-unavailable) reflow success must be unaffected by the
        new code path. Verify no regression when reflow returns (True, rect).
        """
        # Do NOT patch reflow — let the real implementation run.
        # For a plain Helvetica PDF, reflow should succeed (or legacy should).
        result = _apply_replace_to_open_doc(
            self.doc,
            target_text="HELLO",
            replacement_text="WORLD",
            page_number=1,
            manual_overrides={"fail_on_font_unavailable": True},
        )
        # Either reflow or legacy succeeded — the key point is no spurious failure.
        self.assertTrue(
            result["success"],
            f"Unpatched path must still succeed; got: {result}",
        )


if __name__ == "__main__":
    unittest.main()
