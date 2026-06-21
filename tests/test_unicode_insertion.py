"""Regression tests for Unicode-safe text insertion.

Base-14 / simple PDF fonts encode through a one-byte table, so plain
page.insert_text() substitutes a bullet for "smart" punctuation and accents
(curly quotes, em/en dashes, accented letters). reflow._insert_text_unicode_safe
routes such text through an embedded TextWriter face so it renders correctly,
while keeping the exact insert_text path for pure Latin-1 text.

These tests pin both halves of that contract: the special glyphs render (and
differ from the broken base-14 output), and ASCII text is byte-for-byte
unchanged so nothing else can regress.
"""
import os
import sys

import fitz

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "Sources", "Marcedit", "python_site"))
from editor_pkg.reflow import _insert_text_unicode_safe  # noqa: E402


def _ink_pixels(draw):
    """Render a 200x60 page after running *draw(page)* and return the dark-pixel set."""
    doc = fitz.open()
    page = doc.new_page(width=200, height=60)
    draw(page)
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
    s = pix.samples
    dark = set()
    stride = pix.width * pix.n
    for y in range(pix.height):
        for x in range(pix.width):
            j = y * stride + x * pix.n
            if (s[j] + s[j + 1] + s[j + 2]) // 3 < 128:
                dark.add((x, y))
    doc.close()
    return dark


def test_curly_quotes_render_not_bullets():
    """Curly quotes via the helper must match a real TextWriter face, not the
    base-14 bullet substitution that plain insert_text produces."""
    text = "“Company”"  # "Company" in curly quotes

    helper = _ink_pixels(lambda p: _insert_text_unicode_safe(
        p, (10, 40), text, "tibo", 18, (0, 0, 0)))

    def _textwriter_ref(p):
        tw = fitz.TextWriter(p.rect)
        tw.append((10, 40), text, font=fitz.Font("tibo"), fontsize=18)
        tw.write_text(p)
    reference = _ink_pixels(_textwriter_ref)

    base14 = _ink_pixels(lambda p: p.insert_text((10, 40), text, fontname="tibo", fontsize=18))

    # The helper must reproduce the correct (TextWriter) rendering ...
    inter = len(helper & reference)
    assert inter > 0.95 * len(reference), "helper output should match the embedded TextWriter face"
    # ... and must NOT look like the broken base-14 (bullet) rendering.
    assert helper != base14, "helper must differ from the base-14 bullet substitution"


def test_helper_reports_unicode_path():
    """Returns True only when it actually had to take the Unicode path."""
    doc = fitz.open()
    page = doc.new_page()
    assert _insert_text_unicode_safe(page, (10, 40), "plain ascii", "helv", 12, (0, 0, 0)) is False
    assert _insert_text_unicode_safe(page, (10, 60), "em—dash", "helv", 12, (0, 0, 0)) is True
    doc.close()


def test_ascii_passthrough_is_byte_identical():
    """For Latin-1 text the helper must render identically to plain insert_text,
    so the 99% common path can never regress."""
    text = "Acme Holdings Inc."
    helper = _ink_pixels(lambda p: _insert_text_unicode_safe(
        p, (10, 40), text, "helv", 14, (0, 0, 0)))
    plain = _ink_pixels(lambda p: p.insert_text((10, 40), text, fontname="helv", fontsize=14))
    assert helper == plain, "ASCII text must render identically to the original insert_text path"


def test_unicode_safe_never_raises_on_unloadable_font():
    """An internal resource name (e.g. 'R0') with no buffer must still land the
    text rather than raising."""
    doc = fitz.open()
    page = doc.new_page()
    # Should fall back to a Unicode face (helv) and not raise.
    _insert_text_unicode_safe(page, (10, 40), "café “x”", "R0", 12, (0, 0, 0))
    doc.close()
