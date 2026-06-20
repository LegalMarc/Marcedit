#!/usr/bin/env python3
"""
Regression test for issue #31: Reflow-trust override must not suppress
genuine major collisions (>20% overlap).

The fix lives in the REFLOW TRUST block of core.py
(_apply_replace_to_open_doc).  These tests:

  1. Exercise optical.detect_visual_collision directly to confirm the
     >20% threshold returns (True, "Major collision: ...").
  2. Reproduce the exact decision logic from the patched REFLOW TRUST
     block in isolation, proving that a major collision is NOT cleared
     even when reflow_confirmed=True and is_identity_edit=False and
     is_prefix_shrink=False.
  3. Confirm that identity/prefix-shrink edits remain permitted (no
     regression on the legitimate suppression paths).
  4. Drive the REAL _apply_replace_to_open_doc with reflow_confirmed=True
     and a synthetic major-collision signal to prove the patched elif-branch
     in core.py is exercised (the test fails if that branch is removed).
"""

import sys
import os
import tempfile
import unittest
from unittest.mock import patch

python_site = os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site')
sys.path.insert(0, python_site)

import fitz
from editor_pkg import optical
from editor_pkg.core import _apply_replace_to_open_doc


# ---------------------------------------------------------------------------
# Pixmap helpers
# ---------------------------------------------------------------------------

def _make_pixmaps(width=300, height=100, old_box=None, new_box=None):
    """Return (before_pix, after_pix) with solid black rectangles."""
    doc = fitz.open()

    # before
    page = doc.new_page(width=width, height=height)
    if old_box:
        x, y, w, h = old_box
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x, y, x + w, y + h))
        shape.finish(fill=(0, 0, 0))
        shape.commit()
    before_pix = page.get_pixmap()

    # after (new page)
    page = doc.new_page(width=width, height=height)
    if new_box:
        x, y, w, h = new_box
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x, y, x + w, y + h))
        shape.finish(fill=(0, 0, 0))
        shape.commit()
    after_pix = page.get_pixmap()

    doc.close()
    return before_pix, after_pix


# ---------------------------------------------------------------------------
# Helper: reproduce the patched REFLOW TRUST decision logic
# ---------------------------------------------------------------------------

def _apply_reflow_trust(has_collision: bool, msg: str,
                        reflow_confirmed: bool,
                        is_identity_edit: bool,
                        is_prefix_shrink: bool) -> tuple:
    """
    Mirror the patched REFLOW TRUST block from core.py.

    Returns (has_collision_after, logged_reason) so tests can assert on
    both the outcome and which branch was taken.
    """
    is_major_collision = "Major collision" in msg
    logged_reason = None

    if has_collision and reflow_confirmed:
        if is_identity_edit:
            logged_reason = "identity"
            has_collision = False
        elif is_prefix_shrink:
            logged_reason = "prefix_shrink"
            has_collision = False
        elif is_major_collision:
            logged_reason = "major_not_suppressed"
            # has_collision stays True
        else:
            logged_reason = "minor_moderate_suppressed"
            has_collision = False

    return has_collision, logged_reason


# ---------------------------------------------------------------------------
# Part 1: optical layer — major collision is always True regardless of
#         allow_warning
# ---------------------------------------------------------------------------

def _make_pixmaps_multi(before_rects, after_rects, width=400, height=100):
    """Return (before_pix, after_pix) filling the listed fitz.Rect tuples (x0,y0,x1,y1)."""
    doc = fitz.open()

    page = doc.new_page(width=width, height=height)
    for r in before_rects:
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(*r))
        shape.finish(fill=(0, 0, 0))
        shape.commit()
    before_pix = page.get_pixmap()

    page = doc.new_page(width=width, height=height)
    for r in after_rects:
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(*r))
        shape.finish(fill=(0, 0, 0))
        shape.commit()
    after_pix = page.get_pixmap()

    doc.close()
    return before_pix, after_pix


def test_optical_major_collision_is_always_true():
    """
    detect_visual_collision must return (True, 'Major collision: ...')
    for >20% overlap even when allow_warning=True.

    Geometry: a static block (100, 10, 200, 70) plus a new block shifted
    left by 10 px (90, 10, 190, 70).  The exclusive-new pixels at x=90..100
    are all adjacent to the static block, yielding ~28% collision ratio.

    This ensures the detector itself is sound before we test the
    suppression logic on top of it.
    """
    before_pix, after_pix = _make_pixmaps_multi(
        before_rects=[(100, 10, 200, 70)],
        after_rects=[(100, 10, 200, 70), (90, 10, 190, 70)],
    )

    has_col, msg = optical.detect_visual_collision(
        before_pix, after_pix, allow_warning=True
    )

    assert has_col, (
        f"Major collision (>20% overlap) must return has_collision=True "
        f"even with allow_warning=True, got: {msg}"
    )
    assert "Major collision" in msg, (
        f"Expected 'Major collision' in message, got: {msg!r}"
    )


# ---------------------------------------------------------------------------
# Part 2: REFLOW TRUST decision logic
# ---------------------------------------------------------------------------

def test_major_collision_not_suppressed_by_reflow():
    """
    Core fix: a genuine major collision must NOT be cleared when
    reflow_confirmed=True and the edit is neither an identity edit nor
    a prefix shrink.
    """
    # Simulate the optical result a wide replacement would produce
    msg = "Major collision: 1500 pixels (45.2% of new content). Suggestion: Text overlaps existing content significantly - choose different location or reduce text size."
    has_collision = True
    reflow_confirmed = True
    is_identity_edit = False
    is_prefix_shrink = False

    result, reason = _apply_reflow_trust(
        has_collision, msg, reflow_confirmed, is_identity_edit, is_prefix_shrink
    )

    assert result is True, (
        "Major collision must NOT be suppressed by reflow trust; "
        f"has_collision should remain True, got {result} (reason={reason})"
    )
    assert reason == "major_not_suppressed", (
        f"Expected branch 'major_not_suppressed', got {reason!r}"
    )


def test_minor_collision_still_suppressed_by_reflow():
    """
    Non-regression: a minor/moderate collision message (not 'Major collision')
    IS still suppressed when reflow succeeded and the edit is a general one.
    """
    msg = "Moderate overlap: 80 pixels (12.3% of new content) - review recommended"
    has_collision = True
    reflow_confirmed = True
    is_identity_edit = False
    is_prefix_shrink = False

    result, reason = _apply_reflow_trust(
        has_collision, msg, reflow_confirmed, is_identity_edit, is_prefix_shrink
    )

    assert result is False, (
        "Minor/moderate collision should still be suppressed by reflow trust; "
        f"has_collision should be False, got {result} (reason={reason})"
    )
    assert reason == "minor_moderate_suppressed"


def test_identity_edit_major_collision_suppressed():
    """
    Non-regression: identity edits (target == replacement) are structurally
    safe and must still be permitted, even when optical reports a major
    collision (common for in-place font-substitution edits).
    """
    msg = "Major collision: 2000 pixels (55.0% of new content). Suggestion: Text overlaps existing content significantly."
    has_collision = True
    reflow_confirmed = True
    is_identity_edit = True
    is_prefix_shrink = False

    result, reason = _apply_reflow_trust(
        has_collision, msg, reflow_confirmed, is_identity_edit, is_prefix_shrink
    )

    assert result is False, (
        "Identity edit must still be permitted despite major collision; "
        f"has_collision should be False, got {result} (reason={reason})"
    )
    assert reason == "identity"


def test_prefix_shrink_major_collision_suppressed():
    """
    Non-regression: prefix-shrink edits (e.g. 'Philadelphia' -> 'Phila')
    are safe (replacement is shorter) and must still be permitted.
    """
    msg = "Major collision: 900 pixels (22.1% of new content). Suggestion: Text overlaps existing content significantly."
    has_collision = True
    reflow_confirmed = True
    is_identity_edit = False
    is_prefix_shrink = True

    result, reason = _apply_reflow_trust(
        has_collision, msg, reflow_confirmed, is_identity_edit, is_prefix_shrink
    )

    assert result is False, (
        "Prefix-shrink must still be permitted despite major collision; "
        f"has_collision should be False, got {result} (reason={reason})"
    )
    assert reason == "prefix_shrink"


def test_no_collision_no_change():
    """
    When has_collision is False to begin with, the block must not
    touch it regardless of other flags.
    """
    msg = "Clean edit"
    has_collision = False
    reflow_confirmed = True
    is_identity_edit = False
    is_prefix_shrink = False

    result, reason = _apply_reflow_trust(
        has_collision, msg, reflow_confirmed, is_identity_edit, is_prefix_shrink
    )

    assert result is False
    assert reason is None


def test_major_collision_no_reflow_not_suppressed():
    """
    When reflow_confirmed=False the REFLOW TRUST block is skipped
    entirely; a major collision must remain flagged.
    """
    msg = "Major collision: 1200 pixels (30.0% of new content). Suggestion: Text overlaps existing content significantly."
    has_collision = True
    reflow_confirmed = False
    is_identity_edit = False
    is_prefix_shrink = False

    result, reason = _apply_reflow_trust(
        has_collision, msg, reflow_confirmed, is_identity_edit, is_prefix_shrink
    )

    assert result is True
    assert reason is None  # block never entered


# ---------------------------------------------------------------------------
# Part 3: Integration — real _apply_replace_to_open_doc path
# ---------------------------------------------------------------------------
#
# These tests drive the ACTUAL patched code in core.py, not the hand-written
# reimplementation above.  They fail if the elif-is_major_collision branch is
# removed from the REFLOW TRUST block, which is exactly the regression proof
# required by issue #31 acceptance criterion #3.
#
# The approach mirrors tests/test_font_unavailable.py: construct an in-memory
# PDF headlessly with PyMuPDF, patch the two I/O-bound collaborators
# (reflow.reflow_line → simulates reflow success; optical.detect_visual_collision
# → simulates major collision signal), and assert on the returned dict.
# No display, no real files, no XCUITest infrastructure required.
# ---------------------------------------------------------------------------

_MAJOR_COLLISION_MSG = (
    "Major collision: 9999 pixels (55.0% of new content). "
    "Suggestion: Text overlaps existing content significantly - "
    "choose different location or reduce text size."
)


def _build_pdf_with_token(token: str = "HELLO") -> fitz.Document:
    """Return an in-memory fitz.Document with one page containing token."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 200), token, fontsize=14)
    return doc


def _make_dummy_pixmap() -> fitz.Pixmap:
    """Return a minimal valid fitz.Pixmap (a tiny white image)."""
    doc = fitz.open()
    page = doc.new_page(width=50, height=20)
    pix = page.get_pixmap()
    doc.close()
    return pix


def _reflow_returns_success(page, rect, replacement_text, font_info,
                            debug_log=None, font_buffer=None):
    """Stub: reflow always succeeds, returning a plausible result rect."""
    if debug_log is not None:
        debug_log.append("Stub: reflow_line returning success=True")
    return True, fitz.Rect(72, 190, 300, 210)


def _collision_returns_major(before_pix, after_pix,
                             sensitivity=10, exclusion_rect=None,
                             allow_warning=False):
    """Stub: optical always reports a major collision (>20%)."""
    return True, _MAJOR_COLLISION_MSG


class TestMajorCollisionIntegration(unittest.TestCase):
    """
    Integration tests that drive _apply_replace_to_open_doc directly.

    The production fix (issue #31) is the elif-is_major_collision branch
    inside the REFLOW TRUST block in core.py.  Removing that branch would
    cause a wide replacement with reflow_confirmed=True to be silently
    accepted (success=True), making test_genuine_major_collision_rejected
    fail — which is the desired regression protection.

    Three collaborators are patched to allow headless, in-memory execution:
    - editor_pkg.core._get_cached_pixmap  → returns None (cache miss, no I/O)
    - editor_pkg.optical.capture_region   → returns a dummy pixmap (no display)
    - editor_pkg.reflow.reflow_line       → returns success/failure as needed
    - editor_pkg.optical.detect_visual_collision → returns controlled result

    This is the same pattern used by tests/test_font_unavailable.py.
    """

    def setUp(self):
        self.doc = _build_pdf_with_token("HELLO")
        self._dummy_pix = _make_dummy_pixmap()

    def tearDown(self):
        self.doc.close()

    def _patch_optical_pipeline(self, reflow_side_effect, collision_side_effect):
        """Return a context-manager stack that patches all required collaborators.

        Five patches are needed for a fully headless run:
        - _get_cached_pixmap  → return None (cache miss, no file I/O or normpath)
        - _store_cached_pixmap → no-op    (prevent normpath(None) on cache write)
        - optical.capture_region → return a dummy pixmap (no display required)
        - reflow.reflow_line  → caller-supplied stub (controls reflow_confirmed)
        - optical.detect_visual_collision → caller-supplied stub (controls collision)
        """
        from contextlib import ExitStack
        stack = ExitStack()
        # Prevent os.path.normpath(None) exception in the pixmap cache READ
        stack.enter_context(
            patch("editor_pkg.core._get_cached_pixmap", return_value=None)
        )
        # Prevent os.path.normpath(None) exception in the pixmap cache WRITE
        stack.enter_context(
            patch("editor_pkg.core._store_cached_pixmap", return_value=None)
        )
        # Return a real pixmap so the `if 'before_pix' in locals() and before_pix:`
        # guard in the optical verification block passes
        dummy = self._dummy_pix
        stack.enter_context(
            patch("editor_pkg.optical.capture_region", return_value=dummy)
        )
        stack.enter_context(
            patch("editor_pkg.reflow.reflow_line", side_effect=reflow_side_effect)
        )
        stack.enter_context(
            patch("editor_pkg.optical.detect_visual_collision",
                  side_effect=collision_side_effect)
        )
        return stack

    def test_genuine_major_collision_rejected(self):
        """
        Core regression proof: a wide replacement (non-identity, non-prefix-shrink)
        with reflow_confirmed=True and a >20% optical collision must return
        success=False / 'Visual Collision', NOT be silently accepted.

        This test FAILS if the elif-is_major_collision branch is removed from
        the REFLOW TRUST block in _apply_replace_to_open_doc.
        """
        with self._patch_optical_pipeline(_reflow_returns_success,
                                          _collision_returns_major):
            result = _apply_replace_to_open_doc(
                self.doc,
                target_text="HELLO",
                replacement_text="ZZZZZZZZZZZZ",  # non-identity, non-prefix-shrink
                page_number=1,
                manual_overrides={},
            )

        self.assertFalse(
            result.get("success"),
            f"Major collision with reflow_confirmed=True must return success=False; "
            f"got: {result}",
        )
        msg = result.get("message", "")
        self.assertIn(
            "Visual Collision",
            msg,
            f"Expected 'Visual Collision' in message; got: {msg!r}",
        )

    def test_identity_edit_major_collision_still_accepted(self):
        """
        Non-regression: identity edit (target == replacement) must still be
        permitted even when optical reports a major collision — the identity
        branch fires before is_major_collision is checked.
        """
        with self._patch_optical_pipeline(_reflow_returns_success,
                                          _collision_returns_major):
            result = _apply_replace_to_open_doc(
                self.doc,
                target_text="HELLO",
                replacement_text="HELLO",  # identity
                page_number=1,
                manual_overrides={},
            )

        self.assertTrue(
            result.get("success"),
            f"Identity edit must be accepted despite major collision; got: {result}",
        )

    def test_major_collision_without_reflow_rejected(self):
        """
        Sanity check: a major collision with reflow_confirmed=False must also
        be rejected (the REFLOW TRUST block is never entered, so has_collision
        remains True from the optical detector).
        """
        def _reflow_fails(page, rect, replacement_text, font_info,
                          debug_log=None, font_buffer=None):
            if debug_log is not None:
                debug_log.append("Stub: reflow_line returning failure")
            return False, None

        with self._patch_optical_pipeline(_reflow_fails, _collision_returns_major):
            result = _apply_replace_to_open_doc(
                self.doc,
                target_text="HELLO",
                replacement_text="ZZZZZZZZZZZZ",
                page_number=1,
                manual_overrides={},
            )

        self.assertFalse(
            result.get("success"),
            f"Major collision without reflow must also be rejected; got: {result}",
        )


if __name__ == "__main__":
    unittest.main()
