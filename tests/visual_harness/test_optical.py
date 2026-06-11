import fitz
import sys
import os
from pathlib import Path

# Add python_site to path
sys.path.insert(0, str(Path(os.getcwd()) / "Sources/Marcedit/python_site"))
from editor_pkg import optical

def create_test_pdfs():
    """Create a PDF with known collision scenarios"""
    doc = fitz.open()
    page = doc.new_page()
    
    # 1. Setup 'Before' state: Two words with a gap
    # "Hello     World"
    page.insert_text((50, 100), "Hello", fontsize=20)
    page.insert_text((150, 100), "World", fontsize=20)
    
    rect = fitz.Rect(40, 80, 220, 120)
    pix_before = optical.capture_region(page, rect)
    
    # 2. Scenario A: Good Edit (Fits in gap)
    # "Hello  BIG  World"
    page_good = doc.new_page()
    page_good.insert_text((50, 100), "Hello", fontsize=20)
    page_good.insert_text((150, 100), "World", fontsize=20)
    # Insert in middle, no overlap
    page_good.insert_text((110, 100), "BIG", fontsize=20)
    
    pix_good = optical.capture_region(page_good, rect)
    
    # 3. Scenario B: Bad Edit (Collision)
    # "HelloHUGEWorld" - overlaps "Hello" and "World"
    page_bad = doc.new_page()
    page_bad.insert_text((50, 100), "Hello", fontsize=20)
    page_bad.insert_text((150, 100), "World", fontsize=20)
    # Insert causing overlap
    page_bad.insert_text((90, 100), "HUGECOLLISION", fontsize=20)
    
    pix_bad = optical.capture_region(page_bad, rect)
    
    return pix_before, pix_good, pix_bad

def run_tests():
    print("Running Optical Verification Tests...")
    before, good, bad = create_test_pdfs()
    
    # Test 1: Good Edit
    print("\nTest 1: Clean Edit (Expect False/Success)")
    has_collision, msg = optical.detect_visual_collision(before, good)
    print(f"Collision: {has_collision}")
    print(f"Message: {msg}")
    
    if not has_collision:
        print("PASS")
    else:
        print("FAIL: False positive collision detected")

    # Test 2: Bad Edit
    print("\nTest 2: Collision Edit (Expect True/Failure)")
    has_collision, msg = optical.detect_visual_collision(before, bad)
    print(f"Collision: {has_collision}")
    print(f"Message: {msg}")
    
    if has_collision:
        print("PASS")
    else:
        print("FAIL: Failed to detect collision")

if __name__ == "__main__":
    run_tests()
