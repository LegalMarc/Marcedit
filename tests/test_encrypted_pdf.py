"""
Regression test for issue #26: Detect password-protected PDFs and return a
clear error instead of the misleading "Text not found" message.

Run with:
    pytest tests/test_encrypted_pdf.py -q
"""

import os
import sys
import tempfile
import unittest

import fitz  # PyMuPDF

# ── path setup ────────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SITE = os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site")
if _SITE not in sys.path:
    sys.path.insert(0, _SITE)

from editor_pkg.core import (  # noqa: E402
    replace_text_in_pdf,
    identify_font,
    batch_replace,
    regex_replace,
)


def _make_encrypted_pdf(path: str) -> None:
    """Create a minimal AES-256-encrypted PDF with readable text."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Hello World", fontsize=12)
    d.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner_secret",
        user_pw="user_secret",
    )
    d.close()


class TestPasswordProtectedPDF(unittest.TestCase):
    """Ensure all entry points return a clear error on encrypted PDFs."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.enc_path = os.path.join(self._tmpdir, "encrypted.pdf")
        self.out_path = os.path.join(self._tmpdir, "output.pdf")
        _make_encrypted_pdf(self.enc_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _assert_password_error(self, result: dict, label: str):
        """Assert the result is a clean password-error response."""
        self.assertFalse(
            result.get("success"),
            f"{label}: expected success=False, got {result}",
        )
        msg = (result.get("message") or "").lower()
        self.assertTrue(
            "password" in msg or "encrypted" in msg or "protect" in msg,
            f"{label}: message should mention password/encrypted/protect, got: {result.get('message')!r}",
        )
        self.assertNotIn(
            "text not found",
            msg,
            f"{label}: must not fall back to 'Text not found', got: {result.get('message')!r}",
        )

    # ── replace_text_in_pdf ──────────────────────────────────────────────────

    def test_replace_text_in_pdf_returns_password_error(self):
        result = replace_text_in_pdf(
            self.enc_path, self.out_path, "Hello World", "Goodbye"
        )
        self._assert_password_error(result, "replace_text_in_pdf")

    # ── identify_font ────────────────────────────────────────────────────────

    def test_identify_font_returns_password_error(self):
        result = identify_font(self.enc_path, page_number=1, target_text="Hello World")
        self._assert_password_error(result, "identify_font")

    # ── batch_replace ────────────────────────────────────────────────────────

    def test_batch_replace_returns_password_error(self):
        result = batch_replace(
            self.enc_path,
            self.out_path,
            replacements=[{"target_text": "Hello World", "replacement_text": "Goodbye"}],
        )
        self._assert_password_error(result, "batch_replace")

    # ── regex_replace ────────────────────────────────────────────────────────

    def test_regex_replace_returns_password_error(self):
        result = regex_replace(
            self.enc_path, self.out_path, pattern=r"Hello", replacement="Hi"
        )
        self._assert_password_error(result, "regex_replace")


if __name__ == "__main__":
    unittest.main()
