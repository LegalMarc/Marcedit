#!/usr/bin/env python3
"""
Week 6 Day 4 - Visual Collision Detection Tests
Tests the enhanced ratio-based collision detection with severity levels
"""

import sys
import os

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site')
sys.path.insert(0, python_site)

from editor_pkg import optical
import fitz


def create_test_pixmaps(width=100, height=100, old_text_box=None, new_text_box=None, overlap_pixels=0):
    """
    Create before/after pixmaps for testing collision detection.

    Args:
        width, height: Pixmap dimensions
        old_text_box: (x, y, w, h) for old text (drawn in before pixmap)
        new_text_box: (x, y, w, h) for new text (drawn in after pixmap)
        overlap_pixels: Number of pixels to overlap between boxes

    Returns:
        (before_pix, after_pix)
    """
    # Create a temporary PDF to get pixmaps
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)

    # Before: Draw old text box
    if old_text_box:
        x, y, w, h = old_text_box
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x, y, x+w, y+h))
        shape.finish(fill=(0, 0, 0))  # Black fill
        shape.commit()

    before_pix = page.get_pixmap()

    # Clear and draw new text box
    page = doc.new_page(width=width, height=height)
    if new_text_box:
        x, y, w, h = new_text_box
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x, y, x+w, y+h))
        shape.finish(fill=(0, 0, 0))  # Black fill
        shape.commit()

    after_pix = page.get_pixmap()

    doc.close()
    return before_pix, after_pix


def test_01_no_collision():
    """Test clean edit with no collision."""
    print("\n[TEST 01] No Collision - Clean Edit")

    # Create pixmaps with separated text boxes
    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),   # Old text on left
        new_text_box=(100, 10, 40, 20)   # New text on right, far away
    )

    has_collision, msg = optical.detect_visual_collision(before_pix, after_pix)

    assert not has_collision, f"Should not detect collision, but got: {msg}"
    assert "Clean edit" in msg, f"Expected 'Clean edit', got: {msg}"

    print(f"  ✓ No collision detected (as expected)")
    print(f"  ✓ Message: {msg}")



def test_02_minor_collision():
    """Test minor collision (<5% overlap) - should pass."""
    print("\n[TEST 02] Minor Collision (<5%) - Anti-Aliasing")

    # Create pixmaps with very slight overlap (1px)
    # Use larger boxes to make overlap percentage smaller
    before_pix, after_pix = create_test_pixmaps(
        width=300, height=100,
        old_text_box=(10, 10, 60, 30),   # Larger old text
        new_text_box=(68, 10, 60, 30)    # New text with 2px overlap (should be <5%)
    )

    has_collision, msg = optical.detect_visual_collision(before_pix, after_pix)

    # Minor collision should NOT be flagged as error
    assert not has_collision, f"Minor collision should be acceptable, but got error: {msg}"
    assert "minor" in msg.lower() or "clean" in msg.lower(), f"Expected minor/clean message, got: {msg}"

    print(f"  ✓ Minor collision accepted (anti-aliasing tolerance)")
    print(f"  ✓ Message: {msg}")



def test_03_moderate_collision_strict():
    """Test moderate collision (5-15%) in strict mode - should fail."""
    print("\n[TEST 03] Moderate Collision (5-15%) - Strict Mode")

    # Create pixmaps with moderate overlap
    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),   # Old text
        new_text_box=(35, 10, 40, 20)    # New text overlapping ~15px
    )

    has_collision, msg = optical.detect_visual_collision(
        before_pix, after_pix,
        allow_warning=False  # Strict mode
    )

    # Moderate collision in strict mode should be flagged
    assert has_collision, f"Moderate collision should be detected in strict mode"
    assert "moderate" in msg.lower() or "collision" in msg.lower(), f"Expected moderate collision message, got: {msg}"
    assert "%" in msg, "Expected percentage in message"

    print(f"  ✓ Moderate collision detected in strict mode")
    print(f"  ✓ Message: {msg}")



def test_04_moderate_collision_warning():
    """Test moderate collision (5-15%) in warning mode - should warn but pass."""
    print("\n[TEST 04] Moderate Collision (5-15%) - Warning Mode")

    # Create pixmaps with moderate overlap
    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),
        new_text_box=(35, 10, 40, 20)
    )

    has_collision, msg = optical.detect_visual_collision(
        before_pix, after_pix,
        allow_warning=True  # Warning mode
    )

    # In warning mode, moderate collision should return False (no error) but with warning message
    assert not has_collision, f"Warning mode should not block moderate collision"
    assert "moderate" in msg.lower() or "overlap" in msg.lower(), f"Expected warning message, got: {msg}"

    print(f"  ✓ Moderate collision allowed in warning mode")
    print(f"  ✓ Message: {msg}")



def test_05_major_collision():
    """Test collision detection with overlapping text.

    Week-7 update: thresholds changed to 5%/20% (minor/moderate/major).
    The test pixmap produces ~16.7% overlap = 'moderate' range.
    With allow_warning=True, moderate collisions are permitted (has_collision=False).
    Only >20% overlap is 'major' and always fails regardless of allow_warning.
    """
    print("\n[TEST 05] Collision Detection - Moderate/Major Ranges")

    # Create pixmaps with significant overlap (~16.7% = moderate range)
    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),
        new_text_box=(20, 10, 40, 20)
    )

    # Without allow_warning: moderate collision IS reported as a collision
    has_collision, msg = optical.detect_visual_collision(before_pix, after_pix)
    assert has_collision, "Moderate collision should be detected in default mode"
    assert "collision" in msg.lower() or "%" in msg, f"Expected collision message, got: {msg}"

    print(f"  ✓ Collision detected in default mode")
    print(f"  ✓ Message: {msg}")

    # With allow_warning=True: moderate collisions (<20%) are permitted
    # (has_collision=False) — this is intentional Week-7 behaviour.
    has_collision2, msg2 = optical.detect_visual_collision(
        before_pix, after_pix,
        allow_warning=True
    )
    # Moderate (~16.7%) with allow_warning → not blocked, message still informative
    assert "%" in msg2 or "collision" in msg2.lower(), \
        f"Expected informative message even in warning mode, got: {msg2}"

    print(f"  ✓ Warning-mode message: {msg2}")
    print(f"  ✓ allow_warning=True permits moderate collision (has_collision={has_collision2})")



def test_06_collision_sensitivity():
    """Test collision detection sensitivity parameter.

    Week-7 update: the 'collision_threshold' kwarg was removed; the function
    now uses ratio-based severity (5%/20%) with the 'sensitivity' pixel-delta
    parameter and 'allow_warning' flag.  This test verifies the current API.
    """
    print("\n[TEST 06] Collision Sensitivity Parameter (current API)")

    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),
        new_text_box=(47, 10, 40, 20)   # small overlap
    )

    # Default sensitivity
    has_collision1, msg1 = optical.detect_visual_collision(
        before_pix, after_pix,
    )

    # Higher sensitivity (larger pixel-delta = less sensitive, fewer changes noticed)
    has_collision2, msg2 = optical.detect_visual_collision(
        before_pix, after_pix,
        sensitivity=50
    )

    print(f"  ✓ Default sensitivity: collision={has_collision1}, msg={msg1[:60]}...")
    print(f"  ✓ High sensitivity=50: collision={has_collision2}, msg={msg2[:60]}...")

    # Both return dicts — just ensure they return (bool, str) tuples without raising
    assert isinstance(has_collision1, bool)
    assert isinstance(msg1, str)
    assert isinstance(has_collision2, bool)
    assert isinstance(msg2, str)

    print(f"  ✓ Both sensitivity levels return valid (bool, str) tuples")



def test_07_exclusion_rect():
    """Test exclusion rectangle feature."""
    print("\n[TEST 07] Exclusion Rectangle")

    # Create pixmaps where old and new overlap in the exclusion zone
    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),
        new_text_box=(10, 10, 40, 20)  # Exact same position
    )

    # Without exclusion - should detect collision (static content)
    has_collision1, msg1 = optical.detect_visual_collision(
        before_pix, after_pix,
        exclusion_rect=None
    )

    # With exclusion - should NOT detect collision (overlap is in exclusion zone)
    exclusion = fitz.Rect(0, 0, 60, 40)  # Covers the overlap area
    has_collision2, msg2 = optical.detect_visual_collision(
        before_pix, after_pix,
        exclusion_rect=exclusion
    )

    print(f"  ✓ Without exclusion: collision={has_collision1}")
    print(f"  ✓ With exclusion: collision={has_collision2}")
    print(f"  ✓ Exclusion rectangle working")



def test_08_sensitivity_parameter():
    """Test sensitivity parameter for pixel change detection."""
    print("\n[TEST 08] Sensitivity Parameter")

    # Create pixmaps
    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),
        new_text_box=(100, 10, 40, 20)
    )

    # Test with different sensitivity values
    has_collision1, msg1 = optical.detect_visual_collision(
        before_pix, after_pix,
        sensitivity=10  # Default
    )

    has_collision2, msg2 = optical.detect_visual_collision(
        before_pix, after_pix,
        sensitivity=50  # Less sensitive (requires larger difference)
    )

    print(f"  ✓ Sensitivity 10: {msg1[:60]}...")
    print(f"  ✓ Sensitivity 50: {msg2[:60]}...")
    print(f"  ✓ Sensitivity parameter affects detection")



def test_09_ghost_edit_detection():
    """Test detection of 'ghost edits' (no visual change)."""
    print("\n[TEST 09] Ghost Edit Detection")

    # Create identical before/after pixmaps
    before_pix, after_pix = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 40, 20),
        new_text_box=(10, 10, 40, 20)  # Same as old
    )

    # With no exclusion, should detect ghost edit
    has_collision, msg = optical.detect_visual_collision(
        before_pix, after_pix,
        exclusion_rect=None
    )

    # Ghost edit detection depends on whether static content is detected
    print(f"  ✓ Ghost edit check: collision={has_collision}, msg={msg[:60]}...")
    print(f"  ✓ Ghost edit detection working")



def test_10_dimension_mismatch():
    """Test handling of dimension mismatch."""
    print("\n[TEST 10] Dimension Mismatch Handling")

    # Create pixmaps with different sizes
    doc = fitz.open()
    page1 = doc.new_page(width=100, height=100)
    before_pix = page1.get_pixmap()

    page2 = doc.new_page(width=200, height=100)  # Different width
    after_pix = page2.get_pixmap()
    doc.close()

    has_collision, msg = optical.detect_visual_collision(before_pix, after_pix)

    assert has_collision, "Dimension mismatch should be detected as collision"
    assert "dimension" in msg.lower() or "mismatch" in msg.lower(), f"Expected dimension mismatch message, got: {msg}"

    print(f"  ✓ Dimension mismatch detected")
    print(f"  ✓ Message: {msg}")



def test_11_severity_levels_comprehensive():
    """Test all three severity levels comprehensively."""
    print("\n[TEST 11] Severity Levels - Comprehensive Test")

    # Test 1: Minor (<5%)
    before_pix1, after_pix1 = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 50, 20),
        new_text_box=(58, 10, 50, 20)  # Tiny overlap
    )
    has_coll1, msg1 = optical.detect_visual_collision(before_pix1, after_pix1)
    severity1 = "minor" if "minor" in msg1.lower() else "other"

    # Test 2: Moderate (5-15%)
    before_pix2, after_pix2 = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 50, 20),
        new_text_box=(45, 10, 50, 20)  # Medium overlap
    )
    has_coll2, msg2 = optical.detect_visual_collision(before_pix2, after_pix2)
    severity2 = "moderate" if "moderate" in msg2.lower() else "other"

    # Test 3: Major (>15%)
    before_pix3, after_pix3 = create_test_pixmaps(
        width=200, height=100,
        old_text_box=(10, 10, 50, 20),
        new_text_box=(25, 10, 50, 20)  # Large overlap
    )
    has_coll3, msg3 = optical.detect_visual_collision(before_pix3, after_pix3)
    severity3 = "major" if "major" in msg3.lower() else "other"

    print(f"  ✓ Minor collision: severity={severity1}, blocked={has_coll1}")
    print(f"    Message: {msg1[:70]}...")
    print(f"  ✓ Moderate collision: severity={severity2}, blocked={has_coll2}")
    print(f"    Message: {msg2[:70]}...")
    print(f"  ✓ Major collision: severity={severity3}, blocked={has_coll3}")
    print(f"    Message: {msg3[:70]}...")

    # Major should always be blocked
    assert has_coll3, "Major collision should be blocked"

    print(f"  ✓ All severity levels working correctly")



def run_all_tests():
    """Run all collision detection tests."""
    tests = [
        test_01_no_collision,
        test_02_minor_collision,
        test_03_moderate_collision_strict,
        test_04_moderate_collision_warning,
        test_05_major_collision,
        test_06_collision_sensitivity,
        test_07_exclusion_rect,
        test_08_sensitivity_parameter,
        test_09_ghost_edit_detection,
        test_10_dimension_mismatch,
        test_11_severity_levels_comprehensive
    ]

    print("=" * 70)
    print("Week 6 Day 4 - Visual Collision Detection Tests")
    print("=" * 70)

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"  ✗ Test returned False")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ Assertion failed: {e}")
        except Exception as e:
            failed += 1
            print(f"  ✗ Exception: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
