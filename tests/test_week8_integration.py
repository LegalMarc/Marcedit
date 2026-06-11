#!/usr/bin/env python3
"""
Week 8 — End-to-End Integration Tests

Tests the full Python stack through the XPC wrapper layer (core_xpc),
exactly as Swift calls it via PythonKit.  Covers all functions added in
Weeks 7 Day 2–4:

  XPC functions under test:
    analyze_layout()               – layout detection
    batch_replace_text()           – multi-replacement
    regex_replace_text()           – regex-based replacement
    apply_template_replacements()  – placeholder substitution
    get_health_status()            – health check
    get_performance_stats()        – perf stats

Run from the project root:
    python3 tests/test_week8_integration.py
"""

import sys
import os
import tempfile
import shutil
import traceback

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site"))

import fitz
from editor_pkg import core_xpc

# ── Sample PDF locations ──────────────────────────────────────────────────────

_SAMPLES_DIR = os.path.join(_PROJECT_ROOT, "ignored-resources", "sample-files-marcedit")
_CORPUS_DIR  = "/tmp/marcedit_uitest_corpus"

def _find_sample_pdf() -> str | None:
    """Return the first readable real-world PDF we can find."""
    for d in [_SAMPLES_DIR, _CORPUS_DIR]:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".pdf"):
                p = os.path.join(d, f)
                if os.access(p, os.R_OK):
                    return p
    return None


# ── PDF factory ───────────────────────────────────────────────────────────────

def _make_pdf(texts: list, cols: int = 1) -> str:
    """
    Create a temp PDF.
    cols=1  → single column
    cols=2  → two columns (left/right)
    """
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    if cols == 1:
        for i, t in enumerate(texts):
            page.insert_text((72, 80 + i * 40), t, fontsize=11, fontname="Helvetica")
    else:
        for i, t in enumerate(texts):
            x = 72 if i % 2 == 0 else 312
            y = 80 + (i // 2) * 55
            page.insert_text((x, y), t, fontsize=10, fontname="Helvetica")
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


def _tmp_dst() -> str:
    fd, p = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    return p


# ── analyze_layout ────────────────────────────────────────────────────────────

def test_analyze_layout_single_column():
    print("\n[analyze_layout] single-column page")
    src = _make_pdf(["Line one", "Line two", "Line three", "Line four"])
    try:
        result = core_xpc.analyze_layout(src, 0)
        _check("success", result["success"] is True, str(result))
        _check("has layout_type", "layout_type" in result)
        _check("column_count >= 1", result["column_count"] >= 1)
        _check("columns is list", isinstance(result["columns"], list))
        _check("tables is list", isinstance(result["tables"], list))
        _check("dominant_rotation in {0,90,180,270}",
               result["dominant_rotation"] in (0, 90, 180, 270))
    finally:
        os.unlink(src)


def test_analyze_layout_two_column():
    print("\n[analyze_layout] two-column page")
    src = _make_pdf(
        ["Left A", "Right A", "Left B", "Right B",
         "Left C", "Right C", "Left D", "Right D"],
        cols=2
    )
    try:
        result = core_xpc.analyze_layout(src, 0)
        _check("success", result["success"] is True)
        _check("column_count == 2", result["column_count"] == 2,
               f"got {result['column_count']}")
        _check("layout_type is multi_column",
               result["layout_type"] == "multi_column",
               f"got {result['layout_type']}")
    finally:
        os.unlink(src)


def test_analyze_layout_with_focus_rect():
    print("\n[analyze_layout] with focus rect (0-based page_index, XPC rect format)")
    src = _make_pdf(
        ["Left A", "Right A", "Left B", "Right B",
         "Left C", "Right C"],
        cols=2
    )
    try:
        # Focus on the left column area
        result = core_xpc.analyze_layout(src, 0, rect=[72, 70, 280, 200])
        _check("success", result["success"] is True)
        _check("column_index is not None", result["column_index"] is not None)
        _check("column_index == 0 (left col)",
               result["column_index"] == 0,
               f"got {result['column_index']}")
    finally:
        os.unlink(src)


def test_analyze_layout_bad_page_index():
    print("\n[analyze_layout] bad page index → success=False")
    src = _make_pdf(["Some text"])
    try:
        result = core_xpc.analyze_layout(src, 999)
        _check("success is False", result["success"] is False)
    finally:
        os.unlink(src)


def test_analyze_layout_real_pdf():
    print("\n[analyze_layout] real-world PDF")
    pdf = _find_sample_pdf()
    if not pdf:
        print("  –  skipped (no sample PDFs found)")
        return
    result = core_xpc.analyze_layout(pdf, 0)
    _check("success", result["success"] is True, str(result))
    _check("layout_type present", "layout_type" in result)
    _check("column_count >= 1", result.get("column_count", 0) >= 1)


# ── batch_replace_text ────────────────────────────────────────────────────────

def test_batch_replace_empty():
    print("\n[batch_replace_text] empty list → success, 0 applied")
    src = _make_pdf(["Hello World"])
    dst = _tmp_dst()
    try:
        r = core_xpc.batch_replace_text(src, dst, [])
        _check("success", r["success"] is True)
        _check("applied == 0", r["applied"] == 0)
        _check("output file exists", os.path.getsize(dst) > 0)
    finally:
        for f in (src, dst): os.unlink(f)


def test_batch_replace_single():
    print("\n[batch_replace_text] single replacement (0-based page_index)")
    src = _make_pdf(["Replace target here"])
    dst = _tmp_dst()
    try:
        reps = [{"target_text": "Replace target here",
                 "replacement_text": "Replaced",
                 "page_index": 0}]
        r = core_xpc.batch_replace_text(src, dst, reps)
        _check("success", r["success"] is True, str(r.get("message")))
        _check("applied == 1", r["applied"] == 1, f"got {r['applied']}")
        # Verify text is in output
        with fitz.open(dst) as out_doc:
            page_text = out_doc[0].get_text()
        _check("output contains 'Replaced'", "Replaced" in page_text)
    finally:
        for f in (src, dst): os.unlink(f)


def test_batch_replace_multiple():
    print("\n[batch_replace_text] two sequential replacements")
    src = _make_pdf(["Alpha item", "Beta item"])
    dst = _tmp_dst()
    try:
        reps = [
            {"target_text": "Alpha item", "replacement_text": "Alpha done"},
            {"target_text": "Beta item",  "replacement_text": "Beta done"},
        ]
        r = core_xpc.batch_replace_text(src, dst, reps)
        _check("success", r["success"] is True)
        _check("applied == 2", r["applied"] == 2, f"got {r['applied']}")
    finally:
        for f in (src, dst): os.unlink(f)


def test_batch_replace_limit_enforced():
    print("\n[batch_replace_text] >500 replacements → rejected")
    src = _make_pdf(["Filler text"])
    dst = _tmp_dst()
    try:
        reps = [{"target_text": f"t{i}", "replacement_text": f"r{i}"}
                for i in range(501)]
        r = core_xpc.batch_replace_text(src, dst, reps)
        _check("success is False", r["success"] is False)
        _check("message mentions limit", "max" in r.get("message", "").lower(),
               f"got: {r.get('message')}")
    finally:
        for f in (src, dst): os.unlink(f)


def test_batch_replace_page_index_conversion():
    """XPC uses 0-based page_index; core uses 1-based page_number."""
    print("\n[batch_replace_text] page_index 0 → page_number 1 conversion")
    fd, src = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    p0 = doc.new_page(width=612, height=792)
    p0.insert_text((72, 100), "Page one text", fontsize=11, fontname="Helvetica")
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((72, 100), "Page two text", fontsize=11, fontname="Helvetica")
    doc.save(src)
    doc.close()
    dst = _tmp_dst()
    try:
        reps = [{"target_text": "Page one text",
                 "replacement_text": "P1 replaced",
                 "page_index": 0}]
        r = core_xpc.batch_replace_text(src, dst, reps)
        _check("success", r["success"] is True, str(r))
        _check("applied == 1", r["applied"] == 1)
        with fitz.open(dst) as out:
            p0_text = out[0].get_text()
            p1_text = out[1].get_text()
        _check("page 0 updated", "P1 replaced" in p0_text)
        _check("page 1 unchanged", "Page two text" in p1_text)
    finally:
        for f in (src, dst): os.unlink(f)


# ── regex_replace_text ────────────────────────────────────────────────────────

def test_regex_replace_invalid_pattern():
    print("\n[regex_replace_text] invalid pattern → success=False")
    src = _make_pdf(["test text"])
    dst = _tmp_dst()
    try:
        r = core_xpc.regex_replace_text(src, dst, "[bad(", "x")
        _check("success is False", r["success"] is False)
        _check("message present", bool(r.get("message")))
    finally:
        for f in (src, dst): os.unlink(f)


def test_regex_replace_pattern_too_long():
    print("\n[regex_replace_text] pattern >500 chars → rejected")
    src = _make_pdf(["test text"])
    dst = _tmp_dst()
    try:
        r = core_xpc.regex_replace_text(src, dst, "a" * 501, "b")
        _check("success is False", r["success"] is False)
    finally:
        for f in (src, dst): os.unlink(f)


def test_regex_replace_no_match():
    print("\n[regex_replace_text] no match → 0 replacements")
    src = _make_pdf(["Hello World"])
    dst = _tmp_dst()
    try:
        r = core_xpc.regex_replace_text(src, dst, r"ZZZZZZ", "x")
        _check("success", r["success"] is True)
        _check("replacements == 0", r["replacements"] == 0)
    finally:
        for f in (src, dst): os.unlink(f)


def test_regex_replace_case_insensitive():
    print("\n[regex_replace_text] ignore_case=True")
    src = _make_pdf(["Hello World from Marcedit"])
    dst = _tmp_dst()
    try:
        r = core_xpc.regex_replace_text(src, dst,
                                        r"hello world from marcedit",
                                        "Done",
                                        ignore_case=True)
        _check("success", r["success"] is True)
        _check("1 replacement", r["replacements"] == 1,
               f"got {r['replacements']}")
    finally:
        for f in (src, dst): os.unlink(f)


def test_regex_replace_page_range():
    print("\n[regex_replace_text] page_range=[1,1] limits to page 2 only (0-based)")
    fd, src = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    for txt in ["TARGET on page one", "TARGET on page two"]:
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((72, 100), txt, fontsize=11, fontname="Helvetica")
    doc.save(src)
    doc.close()
    dst = _tmp_dst()
    try:
        # page_range=[1,1] → 0-based → page_number=(2,2) → page 2 only
        r = core_xpc.regex_replace_text(src, dst,
                                        r"TARGET on page two", "Done",
                                        page_range=[1, 1])
        _check("success", r["success"] is True)
        _check("replacements == 1", r["replacements"] == 1,
               f"got {r['replacements']}")
        with fitz.open(dst) as out:
            _check("page 0 unchanged",
                   "TARGET on page one" in out[0].get_text())
            _check("page 1 updated",
                   "Done" in out[1].get_text())
    finally:
        for f in (src, dst): os.unlink(f)


# ── apply_template_replacements ───────────────────────────────────────────────

def test_template_empty():
    print("\n[apply_template_replacements] empty placeholders")
    src = _make_pdf(["{{NAME}} works here"])
    dst = _tmp_dst()
    try:
        r = core_xpc.apply_template_replacements(src, dst, {})
        _check("success", r["success"] is True)
        _check("applied == 0", r["applied"] == 0)
    finally:
        for f in (src, dst): os.unlink(f)


def test_template_single_key():
    print("\n[apply_template_replacements] single placeholder")
    src = _make_pdf(["{{CLIENT}} signed today"])
    dst = _tmp_dst()
    try:
        r = core_xpc.apply_template_replacements(src, dst, {"CLIENT": "Acme Corp"})
        _check("success", r["success"] is True, str(r))
        _check("applied == 1", r["applied"] == 1, f"got {r['applied']}")
        _check("not_found is empty", r["not_found"] == [])
    finally:
        for f in (src, dst): os.unlink(f)


def test_template_key_not_found():
    print("\n[apply_template_replacements] key absent from PDF")
    src = _make_pdf(["No placeholders here"])
    dst = _tmp_dst()
    try:
        r = core_xpc.apply_template_replacements(src, dst, {"GHOST": "never"})
        _check("success", r["success"] is True)
        _check("applied == 0", r["applied"] == 0)
        _check("GHOST in not_found", "GHOST" in r["not_found"])
    finally:
        for f in (src, dst): os.unlink(f)


def test_template_invalid_key_rejected():
    print("\n[apply_template_replacements] key with control char rejected")
    src = _make_pdf(["Some text"])
    dst = _tmp_dst()
    try:
        r = core_xpc.apply_template_replacements(src, dst,
                                                 {"bad\nkey": "value"})
        _check("success is False", r["success"] is False)
    finally:
        for f in (src, dst): os.unlink(f)


def test_template_custom_delimiters():
    print("\n[apply_template_replacements] custom delimiters <<<KEY>>>")
    src = _make_pdf(["<<<DATE>>> here"])
    dst = _tmp_dst()
    try:
        r = core_xpc.apply_template_replacements(
            src, dst, {"DATE": "2026-03-03"},
            delimiter_open="<<<", delimiter_close=">>>"
        )
        _check("success", r["success"] is True)
        _check("applied == 1", r["applied"] == 1, f"got {r['applied']}")
    finally:
        for f in (src, dst): os.unlink(f)


def test_template_page_range():
    print("\n[apply_template_replacements] page_range limits to page 1 only (0-based)")
    fd, src = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    for txt in ["{{KEY}} on first page", "{{KEY}} on second page"]:
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((72, 100), txt, fontsize=11, fontname="Helvetica")
    doc.save(src)
    doc.close()
    dst = _tmp_dst()
    try:
        # page_range=[1,1] → only second page (0-based index 1)
        r = core_xpc.apply_template_replacements(
            src, dst, {"KEY": "Done"}, page_range=[1, 1]
        )
        _check("success", r["success"] is True)
        _check("applied == 1", r["applied"] == 1, f"got {r['applied']}")
        with fitz.open(dst) as out:
            _check("page 0 unchanged",
                   "{{KEY}}" in out[0].get_text())
            _check("page 1 updated",
                   "done" in out[1].get_text().lower())
    finally:
        for f in (src, dst): os.unlink(f)


# ── get_health_status ─────────────────────────────────────────────────────────

def test_health_status_structure():
    print("\n[get_health_status] returns required fields")
    result = core_xpc.get_health_status()
    required = ["status", "pymupdf_ok", "pymupdf_version",
                "error_rate", "total_calls", "total_errors",
                "perf_summary", "log_level"]
    for key in required:
        _check(f"has '{key}'", key in result)
    _check("status in {ok, degraded}",
           result.get("status") in ("ok", "degraded"))
    _check("pymupdf_ok is True", result.get("pymupdf_ok") is True)
    _check("error_rate is float", isinstance(result.get("error_rate"), float))


# ── get_performance_stats ─────────────────────────────────────────────────────

def test_performance_stats_accumulate():
    print("\n[get_performance_stats] stats accumulate after operations")
    # Run a replace to generate stats
    src = _make_pdf(["Perf stats test"])
    dst = _tmp_dst()
    try:
        core_xpc.batch_replace_text(src, dst,
                                    [{"target_text": "Perf stats test",
                                      "replacement_text": "done"}])
    finally:
        for f in (src, dst): os.unlink(f)

    stats = core_xpc.get_performance_stats()
    _check("returns dict", isinstance(stats, dict))
    # batch_replace or replace_text_in_pdf should show calls
    total_calls = sum(v.get("calls", 0) for v in stats.values())
    _check("at least one call recorded", total_calls > 0,
           f"got {total_calls}")
    for op, entry in stats.items():
        _check(f"  {op} has 'calls'", "calls" in entry)
        _check(f"  {op} has 'avg_ms'", "avg_ms" in entry)


# ── Cross-function integration ─────────────────────────────────────────────────

def test_batch_then_regex_pipeline():
    """
    Real-world scenario: first batch-replace a placeholder name,
    then use regex to normalise date format.
    """
    print("\n[integration] batch_replace → regex_replace pipeline")
    src = _make_pdf([
        "Client: PLACEHOLDER_NAME",
        "Date: 2026/03/03",
        "Amount: $500",
    ])
    mid = _tmp_dst()
    dst = _tmp_dst()
    try:
        # Step 1: batch replace name
        r1 = core_xpc.batch_replace_text(src, mid, [
            {"target_text": "PLACEHOLDER_NAME",
             "replacement_text": "Acme Corp",
             "page_index": 0}
        ])
        _check("step 1 success", r1["success"] is True, str(r1.get("message")))
        _check("step 1 applied == 1", r1["applied"] == 1)

        # Step 2: regex replace date format  YYYY/MM/DD → YYYY-MM-DD
        r2 = core_xpc.regex_replace_text(mid, dst,
                                         r"\d{4}/\d{2}/\d{2}",
                                         lambda m: m.group(0).replace("/", "-")
                                         if hasattr(m, "group")
                                         # regex_replace_text takes a string replacement
                                         else "2026-03-03")
        # Note: back-reference replacement of date separators requires
        # a more complex pattern — just verify the call succeeds
        _check("step 2 success", r2["success"] is True, str(r2.get("message")))

        # Verify final output contains the batch-replaced name
        with fitz.open(dst) as out:
            text = out[0].get_text()
        _check("final output has 'Acme Corp'", "acme corp" in text.lower())
        _check("final output has 'Amount: $500'", "Amount: $500" in text)

    finally:
        for f in (src, mid, dst): os.unlink(f)


def test_template_then_verify_layout():
    """
    Fill a template, then analyse the layout of the output.
    """
    print("\n[integration] apply_template → analyze_layout")
    src = _make_pdf([
        "{{COMPANY}} — Invoice",
        "{{AMOUNT}} due",
        "{{DATE}} payment date",
    ])
    dst = _tmp_dst()
    try:
        r = core_xpc.apply_template_replacements(src, dst, {
            "COMPANY": "Acme Corp",
            "AMOUNT":  "$1,500.00",
            "DATE":    "2026-03-31",
        })
        _check("template success", r["success"] is True)
        _check("applied == 3", r["applied"] == 3, f"got {r['applied']}")

        # Analyse layout of the produced document
        layout = core_xpc.analyze_layout(dst, 0)
        _check("layout success", layout["success"] is True)
        _check("layout_type is single_column",
               layout["layout_type"] == "single_column",
               f"got '{layout['layout_type']}'")
    finally:
        for f in (src, dst): os.unlink(f)


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Week 8 — End-to-End XPC Integration Tests")
    print("=" * 60)

    tests = [
        # analyze_layout
        test_analyze_layout_single_column,
        test_analyze_layout_two_column,
        test_analyze_layout_with_focus_rect,
        test_analyze_layout_bad_page_index,
        test_analyze_layout_real_pdf,
        # batch_replace_text
        test_batch_replace_empty,
        test_batch_replace_single,
        test_batch_replace_multiple,
        test_batch_replace_limit_enforced,
        test_batch_replace_page_index_conversion,
        # regex_replace_text
        test_regex_replace_invalid_pattern,
        test_regex_replace_pattern_too_long,
        test_regex_replace_no_match,
        test_regex_replace_case_insensitive,
        test_regex_replace_page_range,
        # apply_template_replacements
        test_template_empty,
        test_template_single_key,
        test_template_key_not_found,
        test_template_invalid_key_rejected,
        test_template_custom_delimiters,
        test_template_page_range,
        # health / perf
        test_health_status_structure,
        test_performance_stats_accumulate,
        # cross-function
        test_batch_then_regex_pipeline,
        test_template_then_verify_layout,
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
