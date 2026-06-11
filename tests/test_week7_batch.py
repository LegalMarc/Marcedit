#!/usr/bin/env python3
"""
Week 7 Day 3 — Batch Operations Tests

Tests for:
  - batch_replace()
  - regex_replace()
  - apply_template()

Run from the project root:
    python3 tests/test_week7_batch.py
"""

import sys
import os
import tempfile
import traceback

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site"))

import fitz
from editor_pkg import core


# ── PDF factory ───────────────────────────────────────────────────────────────

def _make_pdf(texts: list, path: str = None) -> str:
    """
    Create a one-page PDF containing each string in *texts* on its own line.
    Returns the path.
    """
    if path is None:
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i, text in enumerate(texts):
        page.insert_text((72, 80 + i * 40), text, fontsize=12, fontname="Helvetica")
    doc.save(path)
    doc.close()
    return path


# ── Test helpers ──────────────────────────────────────────────────────────────

_passed = 0
_failed = 0


def _check(name: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        print(f"  ✓  {name}")
        _passed += 1
    else:
        print(f"  ✗  {name}{f' — {detail}' if detail else ''}")
        _failed += 1


# ── batch_replace tests ───────────────────────────────────────────────────────

def test_batch_empty_replacements():
    print("\n[batch_replace] empty list → success, 0 applied")
    src = _make_pdf(["Hello World"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.batch_replace(src, dst, [])
        _check("success", result["success"] is True)
        _check("applied == 0", result["applied"] == 0)
        _check("output file created", os.path.exists(dst) and os.path.getsize(dst) > 0)
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_batch_single_replacement():
    print("\n[batch_replace] single replacement")
    src = _make_pdf(["Replace me please"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        reps = [{"target_text": "Replace me please", "replacement_text": "Done"}]
        result = core.batch_replace(src, dst, reps)
        _check("success", result["success"] is True, str(result.get("message")))
        _check("applied == 1", result["applied"] == 1, f"got {result['applied']}")
        _check("skipped == 0", result["skipped"] == 0)
        _check("one result entry", len(result["results"]) == 1)
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_batch_multiple_replacements():
    print("\n[batch_replace] two sequential replacements")
    src = _make_pdf(["Alpha text here", "Beta text here"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        reps = [
            {"target_text": "Alpha text here", "replacement_text": "Alpha DONE"},
            {"target_text": "Beta text here",  "replacement_text": "Beta DONE"},
        ]
        result = core.batch_replace(src, dst, reps)
        _check("success", result["success"] is True)
        _check("both applied", result["applied"] == 2, f"got {result['applied']}")
        _check("two results", len(result["results"]) == 2)
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_batch_not_found_increments_skipped():
    print("\n[batch_replace] not-found target increments skipped")
    src = _make_pdf(["Only this text"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        reps = [
            {"target_text": "Only this text",  "replacement_text": "Found"},
            {"target_text": "Ghost text XXXXX", "replacement_text": "Won't happen"},
        ]
        result = core.batch_replace(src, dst, reps)
        _check("returns success=True (partial OK)", result["success"] is True)
        _check("skipped == 1", result["skipped"] == 1, f"got {result['skipped']}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_batch_empty_target_skipped():
    print("\n[batch_replace] empty target_text skipped gracefully")
    src = _make_pdf(["Some text"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        reps = [{"target_text": "", "replacement_text": "oops"}]
        result = core.batch_replace(src, dst, reps)
        _check("success", result["success"] is True)
        _check("skipped == 1", result["skipped"] == 1)
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_batch_progress_callback():
    print("\n[batch_replace] progress callback fires")
    src = _make_pdf(["Item One", "Item Two"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    calls = []
    try:
        reps = [
            {"target_text": "Item One", "replacement_text": "1"},
            {"target_text": "Item Two", "replacement_text": "2"},
        ]
        core.batch_replace(src, dst, reps,
                           progress_callback=lambda c, t: calls.append((c, t)))
        _check("callback called twice", len(calls) == 2, f"got {calls}")
        _check("final call is (2, 2)", calls[-1] == (2, 2), f"got {calls[-1]}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


# ── regex_replace tests ───────────────────────────────────────────────────────

def test_regex_bad_pattern():
    print("\n[regex_replace] invalid pattern → success=False")
    src = _make_pdf(["test"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.regex_replace(src, dst, "[invalid(", "x")
        _check("success is False", result["success"] is False)
        _check("message mentions regex", "regex" in result["message"].lower(),
               f"got: {result['message']}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_regex_no_match():
    print("\n[regex_replace] pattern that doesn't match → 0 replacements")
    src = _make_pdf(["Hello World"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.regex_replace(src, dst, r"ZZZZZZ", "x")
        _check("success", result["success"] is True)
        _check("replacements == 0", result["replacements"] == 0)
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_regex_literal_match():
    print("\n[regex_replace] literal pattern match")
    src = _make_pdf(["Replace this word"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.regex_replace(src, dst, r"Replace this word", "Done")
        _check("success", result["success"] is True)
        _check("1 replacement", result["replacements"] == 1,
               f"got {result['replacements']}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_regex_case_insensitive():
    print("\n[regex_replace] case-insensitive flag")
    import re
    src = _make_pdf(["Hello World"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.regex_replace(src, dst, r"hello world", "Hi",
                                    flags=re.IGNORECASE)
        _check("success", result["success"] is True)
        _check("1 replacement (case-insensitive)",
               result["replacements"] == 1, f"got {result['replacements']}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_regex_page_range():
    print("\n[regex_replace] page_range limits search to specific pages")
    fd, src = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    for pg_text in ["TARGET on page 1", "Other on page 2"]:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), pg_text, fontsize=12, fontname="Helvetica")
    doc.save(src)
    doc.close()

    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        # Only search page 2 (1-based: page_range=(2,2))
        result = core.regex_replace(src, dst, r"TARGET on page 1", "X",
                                    page_range=(2, 2))
        _check("success", result["success"] is True)
        _check("0 replacements (out of range)",
               result["replacements"] == 0, f"got {result['replacements']}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


# ── apply_template tests ──────────────────────────────────────────────────────

def test_template_empty_placeholders():
    print("\n[apply_template] empty dict → success, 0 applied")
    src = _make_pdf(["{{NAME}} is great"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.apply_template(src, dst, {})
        _check("success", result["success"] is True)
        _check("applied == 0", result["applied"] == 0)
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_template_single_key():
    print("\n[apply_template] single placeholder")
    src = _make_pdf(["{{CLIENT}} signed the contract"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.apply_template(src, dst, {"CLIENT": "Acme Corp"})
        _check("success", result["success"] is True, str(result))
        _check("applied == 1", result["applied"] == 1, f"got {result['applied']}")
        _check("not_found is empty", result["not_found"] == [])
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_template_missing_key_reported():
    print("\n[apply_template] key not present in PDF → in not_found")
    src = _make_pdf(["No placeholders here"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.apply_template(src, dst, {"GHOST": "never found"})
        _check("success", result["success"] is True)
        _check("applied == 0", result["applied"] == 0)
        _check("GHOST in not_found", "GHOST" in result["not_found"])
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_template_custom_delimiters():
    print("\n[apply_template] custom delimiters <<<KEY>>>")
    src = _make_pdf(["<<<DATE>>> is important"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.apply_template(src, dst, {"DATE": "2026-03-03"},
                                     delimiter_open="<<<", delimiter_close=">>>")
        _check("success", result["success"] is True)
        _check("applied == 1", result["applied"] == 1, f"got {result['applied']}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


def test_template_multiple_keys():
    print("\n[apply_template] two different placeholders")
    src = _make_pdf(["{{FIRST}} and {{SECOND}} are here"])
    fd, dst = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        result = core.apply_template(src, dst,
                                     {"FIRST": "Alpha", "SECOND": "Beta"})
        _check("success", result["success"] is True)
        # Both keys match in the same span, so we expect ≥ 1 applied
        _check("at least one substitution", result["applied"] >= 1,
               f"got {result['applied']}")
    finally:
        for f in (src, dst):
            try: os.unlink(f)
            except OSError: pass


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Week 7 Day 3 — Batch Operations Tests")
    print("=" * 60)

    tests = [
        # batch_replace
        test_batch_empty_replacements,
        test_batch_single_replacement,
        test_batch_multiple_replacements,
        test_batch_not_found_increments_skipped,
        test_batch_empty_target_skipped,
        test_batch_progress_callback,
        # regex_replace
        test_regex_bad_pattern,
        test_regex_no_match,
        test_regex_literal_match,
        test_regex_case_insensitive,
        test_regex_page_range,
        # apply_template
        test_template_empty_placeholders,
        test_template_single_key,
        test_template_missing_key_reported,
        test_template_custom_delimiters,
        test_template_multiple_keys,
    ]

    for t in tests:
        try:
            t()
        except Exception:
            print(f"  ✗  {t.__name__} raised an exception:")
            traceback.print_exc()
            global _failed
            _failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed  "
          f"({_passed}/{_passed + _failed})")
    print("=" * 60)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
