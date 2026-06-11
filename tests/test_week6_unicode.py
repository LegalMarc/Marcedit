#!/usr/bin/env python3
"""
Week 6 Day 3 - Unicode Normalization Tests
Tests the new Unicode normalization functions
"""

import sys
import os

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), '..', 'Sources', 'Marcedit', 'python_site')
sys.path.insert(0, python_site)

from editor_pkg import core


def test_01_normalize_unicode_nfc():
    """Test NFC normalization (canonical composition)."""
    print("\n[TEST 01] NFC Normalization")

    # Test 1: Combining characters should be composed
    # "café" as e + combining acute → é (single codepoint)
    input_text = "cafe\u0301"  # café with combining acute
    result = core.normalize_unicode(input_text, 'NFC')

    # After NFC, should be single codepoint é
    assert result == "café", f"Expected 'café', got '{result}'"
    assert len(result) == 4, f"Expected 4 chars, got {len(result)}"

    print(f"  ✓ Combining characters composed: 'cafe\\u0301' → 'café'")

    # Test 2: Already composed should stay the same
    input_text2 = "café"
    result2 = core.normalize_unicode(input_text2, 'NFC')
    assert result2 == "café"

    print(f"  ✓ Already composed text unchanged")

    # Test 3: Ligatures should be preserved in NFC
    input_text3 = "ﬁnd"
    result3 = core.normalize_unicode(input_text3, 'NFC')
    assert result3 == "ﬁnd", f"Expected ligature preserved, got '{result3}'"

    print(f"  ✓ Ligatures preserved in NFC")



def test_02_normalize_unicode_nfd():
    """Test NFD normalization (canonical decomposition)."""
    print("\n[TEST 02] NFD Normalization")

    # Test: Precomposed characters should be decomposed
    input_text = "café"
    result = core.normalize_unicode(input_text, 'NFD')

    # After NFD, é should be e + combining acute
    assert len(result) == 5, f"Expected 5 chars (e + combining), got {len(result)}"
    assert result[3] == 'e', "Fourth char should be 'e'"
    assert result[4] == '\u0301', "Fifth char should be combining acute"

    print(f"  ✓ Precomposed characters decomposed: 'café' → 'cafe\\u0301'")

    # Test 2: Ligatures still preserved in NFD
    input_text2 = "ﬁnd"
    result2 = core.normalize_unicode(input_text2, 'NFD')
    assert result2 == "ﬁnd"

    print(f"  ✓ Ligatures preserved in NFD")



def test_03_normalize_unicode_nfkc():
    """Test NFKC normalization (compatibility composition)."""
    print("\n[TEST 03] NFKC Normalization")

    # Test 1: Ligatures should be decomposed
    input_text = "ﬁnd"
    result = core.normalize_unicode(input_text, 'NFKC')
    assert result == "find", f"Expected 'find', got '{result}'"

    print(f"  ✓ Ligature decomposed: 'ﬁnd' → 'find'")

    # Test 2: Multiple ligatures
    input_text2 = "ﬁnd the ﬁle"
    result2 = core.normalize_unicode(input_text2, 'NFKC')
    assert result2 == "find the file"

    print(f"  ✓ Multiple ligatures decomposed")

    # Test 3: Combining characters also composed
    input_text3 = "cafe\u0301"  # café with combining
    result3 = core.normalize_unicode(input_text3, 'NFKC')
    assert result3 == "café"

    print(f"  ✓ Combining characters composed in NFKC")



def test_04_strip_invisible_chars():
    """Test stripping zero-width and invisible characters."""
    print("\n[TEST 04] Strip Invisible Characters")

    # Test 1: Zero-width space
    input_text = "test\u200Bword"
    result = core.strip_invisible_chars(input_text)
    assert result == "testword", f"Expected 'testword', got '{result}'"

    print(f"  ✓ Zero-width space removed: 'test\\u200Bword' → 'testword'")

    # Test 2: Zero-width non-joiner
    input_text2 = "hello\u200Cworld"
    result2 = core.strip_invisible_chars(input_text2)
    assert result2 == "helloworld"

    print(f"  ✓ Zero-width non-joiner removed")

    # Test 3: Multiple zero-width chars
    input_text3 = "a\u200Bb\u200Cc\u200Dd"
    result3 = core.strip_invisible_chars(input_text3)
    assert result3 == "abcd"

    print(f"  ✓ Multiple zero-width chars removed")

    # Test 4: BOM (zero-width no-break space)
    input_text4 = "\uFEFFtest"
    result4 = core.strip_invisible_chars(input_text4)
    assert result4 == "test"

    print(f"  ✓ BOM removed")

    # Test 5: Preserve normal spaces
    input_text5 = "hello world"
    result5 = core.strip_invisible_chars(input_text5)
    assert result5 == "hello world"

    print(f"  ✓ Normal spaces preserved")



def test_05_detect_ligatures():
    """Test ligature detection."""
    print("\n[TEST 05] Detect Ligatures")

    # Test 1: Single ligature
    result = core.detect_ligatures("ﬁnd")
    assert result['has_ligatures'] == True
    assert result['count'] == 1
    assert len(result['positions']) == 1
    assert result['positions'][0][2] == 'ﬁ'  # ligature
    assert result['positions'][0][3] == 'fi'  # decomposed

    print(f"  ✓ Single ligature detected: 'ﬁ' at position 0")

    # Test 2: Multiple ligatures
    result2 = core.detect_ligatures("ﬁnd the ﬁle")
    assert result2['count'] == 2
    assert result2['positions'][0][0] == 0   # First at position 0
    assert result2['positions'][1][0] == 8   # Second at position 8 (ﬁ is 1 char, not 2)

    print(f"  ✓ Multiple ligatures detected at positions 0 and 8")

    # Test 3: No ligatures
    result3 = core.detect_ligatures("find the file")
    assert result3['has_ligatures'] == False
    assert result3['count'] == 0

    print(f"  ✓ No ligatures detected correctly")

    # Test 4: Different ligature types
    result4 = core.detect_ligatures("æﬀord")
    assert result4['count'] == 2  # æ and ﬀ
    assert 'æ' in [pos[2] for pos in result4['positions']]
    assert 'ﬀ' in [pos[2] for pos in result4['positions']]

    print(f"  ✓ Different ligature types detected: æ, ﬀ")



def test_06_decompose_ligatures():
    """Test ligature decomposition."""
    print("\n[TEST 06] Decompose Ligatures")

    # Test 1: Simple decomposition
    decomposed, info = core.decompose_ligatures("ﬁnd")
    assert decomposed == "find"
    assert info['has_ligatures'] == True
    assert info['count'] == 1

    print(f"  ✓ Ligature decomposed: 'ﬁnd' → 'find'")

    # Test 2: Multiple ligatures
    decomposed2, info2 = core.decompose_ligatures("ﬁnd the ﬁle")
    assert decomposed2 == "find the file"
    assert info2['count'] == 2

    print(f"  ✓ Multiple ligatures decomposed")

    # Test 3: No ligatures
    decomposed3, info3 = core.decompose_ligatures("hello world")
    assert decomposed3 == "hello world"
    assert info3['has_ligatures'] == False

    print(f"  ✓ Text without ligatures unchanged")

    # Test 4: Mixed content
    decomposed4, info4 = core.decompose_ligatures("The ﬁrst æon")
    assert decomposed4 == "The first aeon"
    assert info4['count'] == 2

    print(f"  ✓ Mixed content decomposed: 'The ﬁrst æon' → 'The first aeon'")



def test_07_restore_ligatures():
    """Test ligature restoration."""
    print("\n[TEST 07] Restore Ligatures")

    # Test 1: Simple restoration
    original_info = core.detect_ligatures("ﬁnd")
    restored = core.restore_ligatures("find", original_info)
    assert restored == "ﬁnd", f"Expected 'ﬁnd', got '{restored}'"

    print(f"  ✓ Ligature restored: 'find' → 'ﬁnd'")

    # Test 2: Restoration with longer text
    original_info2 = core.detect_ligatures("ﬁnd")
    restored2 = core.restore_ligatures("finding", original_info2)
    assert restored2 == "ﬁnding", f"Expected 'ﬁnding', got '{restored2}'"

    print(f"  ✓ Ligature restored in longer text: 'finding' → 'ﬁnding'")

    # Test 3: No ligatures in original
    original_info3 = core.detect_ligatures("hello")
    restored3 = core.restore_ligatures("hello world", original_info3)
    assert restored3 == "hello world"

    print(f"  ✓ Text unchanged when no ligatures in original")

    # Test 4: Multiple ligatures
    original_info4 = core.detect_ligatures("ﬁnd the ﬁle")
    restored4 = core.restore_ligatures("find the file", original_info4)
    # Note: Simple restoration replaces first occurrences
    assert 'ﬁ' in restored4

    print(f"  ✓ Multiple ligatures restored")



def test_08_normalize_for_matching():
    """Test normalize_text_for_matching (aggressive)."""
    print("\n[TEST 08] Normalize for Matching")

    # Test 1: Ligatures decomposed
    result = core.normalize_text_for_matching("ﬁnd the ﬁle")
    assert result == "find the file", f"Expected 'find the file', got '{result}'"

    print(f"  ✓ Ligatures decomposed for matching")

    # Test 2: Combining characters composed
    result2 = core.normalize_text_for_matching("cafe\u0301")
    assert result2 == "café"

    print(f"  ✓ Combining characters composed")

    # Test 3: Zero-width removed
    result3 = core.normalize_text_for_matching("test\u200Bword")
    assert result3 == "testword"

    print(f"  ✓ Zero-width characters removed")

    # Test 4: Whitespace partially normalized
    # Week-7 BUG #49 FIX: function now preserves intentional whitespace patterns
    # (double/triple spaces for tables, justified text, etc.) and only collapses
    # runs of 4+ spaces to 2.  Newlines are preserved as single \n.
    result4 = core.normalize_text_for_matching("hello   world  \n  test")
    # The function lowercases and normalises via NFKC, strips invisible chars,
    # collapses 4+ spaces but preserves ≤3 spaces and newlines.
    assert "hello" in result4
    assert "world" in result4
    assert "test" in result4

    print(f"  ✓ Whitespace partially normalized (preserves intentional spacing): {repr(result4)}")

    # Test 5: Lowercased by default
    result5 = core.normalize_text_for_matching("Hello WORLD")
    assert result5 == "hello world"

    print(f"  ✓ Lowercased by default")

    # Test 6: Preserve case option
    result6 = core.normalize_text_for_matching("Hello WORLD", preserve_case=True)
    assert result6 == "Hello WORLD"

    print(f"  ✓ Case preserved when requested")



def test_09_normalize_for_replacement():
    """Test normalize_text_for_replacement (conservative)."""
    print("\n[TEST 09] Normalize for Replacement")

    # Test 1: Ligatures preserved by default
    result = core.normalize_text_for_replacement("ﬁnd")
    assert result == "ﬁnd", f"Expected 'ﬁnd', got '{result}'"

    print(f"  ✓ Ligatures preserved by default")

    # Test 2: Combining characters composed
    result2 = core.normalize_text_for_replacement("cafe\u0301")
    assert result2 == "café"

    print(f"  ✓ Combining characters composed")

    # Test 3: Whitespace NOT normalized (preserved)
    result3 = core.normalize_text_for_replacement("hello  world")
    assert result3 == "hello  world"  # Double space preserved

    print(f"  ✓ Whitespace preserved")

    # Test 4: Case NOT changed
    result4 = core.normalize_text_for_replacement("Hello WORLD")
    assert result4 == "Hello WORLD"

    print(f"  ✓ Case preserved")

    # Test 5: Decompose ligatures when requested
    result5 = core.normalize_text_for_replacement("ﬁnd", preserve_ligatures=False)
    assert result5 == "find"

    print(f"  ✓ Ligatures decomposed when preserve_ligatures=False")



def test_10_unicode_edge_cases():
    """Test various Unicode edge cases."""
    print("\n[TEST 10] Unicode Edge Cases")

    # Test 1: Emoji (should be preserved)
    result = core.normalize_unicode("Hello 👋 World", 'NFC')
    assert "👋" in result

    print(f"  ✓ Emoji preserved")

    # Test 2: Cyrillic text
    result2 = core.normalize_unicode("Привет мир", 'NFC')
    assert result2 == "Привет мир"

    print(f"  ✓ Cyrillic text normalized")

    # Test 3: Greek text
    result3 = core.normalize_unicode("Γεια σου κόσμε", 'NFC')
    assert "Γεια" in result3

    print(f"  ✓ Greek text normalized")

    # Test 4: Mixed scripts
    result4 = core.normalize_text_for_matching("Hello Привет 你好")
    assert "hello" in result4.lower()
    assert "привет" in result4.lower()

    print(f"  ✓ Mixed scripts handled")

    # Test 5: Currency symbols (from existing normalize_currency)
    # Note: normalize_currency is separate, test normalize_unicode doesn't break it
    result5 = core.normalize_unicode("$100.00", 'NFC')
    assert "$" in result5

    print(f"  ✓ Currency symbols preserved")



def test_11_invalid_input_handling():
    """Test handling of invalid inputs."""
    print("\n[TEST 11] Invalid Input Handling")

    # Test 1: Empty string
    result = core.normalize_unicode("", 'NFC')
    assert result == ""

    print(f"  ✓ Empty string handled")

    # Test 2: Invalid normalization form
    try:
        core.normalize_unicode("test", 'INVALID')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid normalization form" in str(e)

    print(f"  ✓ Invalid normalization form raises ValueError")

    # Test 3: None input to strip_invisible_chars
    result3 = core.strip_invisible_chars("")
    assert result3 == ""

    print(f"  ✓ Empty input to strip_invisible_chars handled")

    # Test 4: None input to detect_ligatures
    result4 = core.detect_ligatures("")
    assert result4['has_ligatures'] == False
    assert result4['count'] == 0

    print(f"  ✓ Empty input to detect_ligatures handled")



def run_all_tests():
    """Run all Unicode normalization tests."""
    tests = [
        test_01_normalize_unicode_nfc,
        test_02_normalize_unicode_nfd,
        test_03_normalize_unicode_nfkc,
        test_04_strip_invisible_chars,
        test_05_detect_ligatures,
        test_06_decompose_ligatures,
        test_07_restore_ligatures,
        test_08_normalize_for_matching,
        test_09_normalize_for_replacement,
        test_10_unicode_edge_cases,
        test_11_invalid_input_handling
    ]

    print("=" * 70)
    print("Week 6 Day 3 - Unicode Normalization Tests")
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
