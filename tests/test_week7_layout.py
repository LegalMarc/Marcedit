#!/usr/bin/env python3
"""
Week 7 Day 2 — Layout Detection Tests

Tests for:
  - detect_columns()
  - get_text_rotation()
  - detect_tables()
  - get_reading_order()
  - detect_layout_context()

Run from the project root:
    python3 tests/test_week7_layout.py
"""

import sys
import os
import tempfile
import traceback

# Resolve python_site relative to this file's location (tests/ → project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site"))

import fitz
from editor_pkg import core


# ── PDF Factories ─────────────────────────────────────────────────────────────

def _make_single_column_pdf() -> str:
    """Simple single-column, horizontal text."""
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(8):
        page.insert_text((72, 80 + i * 60),
                         f"Line {i+1}: The quick brown fox jumps over the lazy dog.",
                         fontsize=11, fontname="Helvetica")
    doc.save(path)
    doc.close()
    return path


def _make_two_column_pdf() -> str:
    """Two-column layout: left column ~72-300 pt, right column ~312-540 pt."""
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(6):
        page.insert_text((72, 80 + i * 55),
                         f"Left col {i+1}: Lorem ipsum dolor sit amet.",
                         fontsize=10, fontname="Helvetica")
        page.insert_text((312, 80 + i * 55),
                         f"Right col {i+1}: Consectetur adipiscing elit.",
                         fontsize=10, fontname="Helvetica")
    doc.save(path)
    doc.close()
    return path


def _make_table_pdf() -> str:
    """Page with a simple 3×3 grid drawn as lines."""
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Draw grid: 3 cols × 3 rows at (100, 100)–(400, 340)
    col_xs = [100, 200, 300, 400]
    row_ys = [100, 180, 260, 340]
    shape = page.new_shape()
    for y in row_ys:
        shape.draw_line(fitz.Point(100, y), fitz.Point(400, y))
    for x in col_xs:
        shape.draw_line(fitz.Point(x, 100), fitz.Point(x, 340))
    shape.finish(color=(0, 0, 0), width=1)
    shape.commit()
    # Add cell labels
    for r in range(3):
        for c in range(3):
            page.insert_text(
                (col_xs[c] + 5, row_ys[r] + 40),
                f"R{r+1}C{c+1}", fontsize=9, fontname="Helvetica"
            )
    doc.save(path)
    doc.close()
    return path


def _make_rotated_text_pdf() -> str:
    """Page with some 90° rotated text inserted via a shape."""
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Normal horizontal text", fontsize=12, fontname="Helvetica")
    # fitz can insert rotated text via morph parameter
    page.insert_text(
        (300, 400), "Rotated 90 degrees",
        fontsize=12, fontname="Helvetica",
        morph=(fitz.Point(300, 400), fitz.Matrix(0, 1, -1, 0, 0, 0))
    )
    doc.save(path)
    doc.close()
    return path


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_detect_columns_single():
    print("\n[detect_columns] single-column page")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            cols = core.detect_columns(page)
        assert isinstance(cols, list), "returns a list"
        assert len(cols) <= 1, f"single column → 0 or 1 column rects; got {len(cols)}"
    finally:
        os.unlink(path)


def test_detect_columns_two():
    print("\n[detect_columns] two-column page")
    path = _make_two_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            cols = core.detect_columns(page)
        assert isinstance(cols, list), "returns a list"
        assert len(cols) == 2, f"detects 2 columns; got {len(cols)}"
        if len(cols) == 2:
            assert cols[0].x0 < cols[1].x0, "left col is left of right col"
    finally:
        os.unlink(path)


def test_get_text_rotation_normal():
    print("\n[get_text_rotation] horizontal span → 0°")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            raw = page.get_text("dict")
            spans = [sp for b in raw["blocks"] if b["type"] == 0
                     for l in b["lines"] for sp in l["spans"]]
        assert len(spans) > 0, "at least one span"
        if spans:
            angle = core.get_text_rotation(spans[0])
            assert isinstance(angle, int), "returns int"
            assert angle == 0, f"normal text is 0°; got {angle}"
    finally:
        os.unlink(path)


def test_get_text_rotation_empty_span():
    print("\n[get_text_rotation] span without 'dir' key → 0°")
    angle = core.get_text_rotation({})
    assert angle == 0, f"returns 0 for missing dir; got {angle}"


def test_detect_tables_no_lines():
    print("\n[detect_tables] page without lines → empty list")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            tables = core.detect_tables(page)
        assert isinstance(tables, list), "returns list"
        assert len(tables) == 0, f"no tables on plain text page; got {len(tables)}"
    finally:
        os.unlink(path)


def test_detect_tables_grid():
    print("\n[detect_tables] page with 3×3 grid")
    path = _make_table_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            tables = core.detect_tables(page)
        assert isinstance(tables, list), "returns list"
        assert len(tables) >= 1, f"detects at least one table; got {len(tables)}"
        if tables:
            t = tables[0]
            assert "rect" in t, "table has 'rect'"
            assert "rows" in t, "table has 'rows'"
            assert "cols" in t, "table has 'cols'"
            assert "cells" in t, "table has 'cells'"
            assert t["rows"] == 3, f"3 rows detected; got {t['rows']}"
            assert t["cols"] == 3, f"3 cols detected; got {t['cols']}"
            assert len(t["cells"]) == 9, f"9 cells; got {len(t['cells'])}"
    finally:
        os.unlink(path)


def test_get_reading_order_single():
    print("\n[get_reading_order] single-column → top-to-bottom")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ordered = core.get_reading_order(page)
        assert isinstance(ordered, list), "returns list"
        assert len(ordered) > 0, "has blocks"
        # Verify top-to-bottom ordering
        ys = [b["bbox"][1] for b in ordered]
        assert ys == sorted(ys), f"y-coordinates non-decreasing; out-of-order: {ys}"
    finally:
        os.unlink(path)


def test_get_reading_order_two_column():
    print("\n[get_reading_order] two-column → left column before right column")
    path = _make_two_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ordered = core.get_reading_order(page)
        assert len(ordered) > 0, "has blocks"
        # First block should be in left column (x0 < 250)
        if ordered:
            assert ordered[0]["bbox"][0] < 250, \
                f"first block is in left column; x0={ordered[0]['bbox'][0]:.1f}"
    finally:
        os.unlink(path)


def test_detect_layout_context_single():
    print("\n[detect_layout_context] single-column page")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ctx = core.detect_layout_context(page)
        required = ["layout_type", "columns", "column_count", "tables",
                    "has_tables", "dominant_rotation", "has_rotated_text",
                    "column_index", "rect_rotation"]
        for key in required:
            assert key in ctx, f"has key '{key}'"
        assert ctx["layout_type"] == "single_column", \
            f"layout_type is 'single_column'; got '{ctx['layout_type']}'"
        assert ctx["dominant_rotation"] == 0, \
            f"dominant_rotation is 0; got {ctx['dominant_rotation']}"
        assert ctx["has_rotated_text"] is False, "has_rotated_text is False"
    finally:
        os.unlink(path)


def test_detect_layout_context_two_column():
    print("\n[detect_layout_context] two-column page")
    path = _make_two_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ctx = core.detect_layout_context(page)
        assert ctx["layout_type"] == "multi_column", \
            f"layout_type is 'multi_column'; got '{ctx['layout_type']}'"
        assert ctx["column_count"] == 2, \
            f"column_count is 2; got {ctx['column_count']}"
    finally:
        os.unlink(path)


def test_detect_layout_context_with_rect():
    print("\n[detect_layout_context] two-column with focus rect")
    path = _make_two_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            # Focus on the left column
            left_rect = fitz.Rect(72, 80, 300, 200)
            ctx = core.detect_layout_context(page, left_rect)
        assert ctx["column_index"] == 0, \
            f"column_index is 0 (left column); got {ctx['column_index']}"
    finally:
        os.unlink(path)


def test_detect_layout_context_table():
    print("\n[detect_layout_context] page with table")
    path = _make_table_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ctx = core.detect_layout_context(page)
        assert ctx["has_tables"] is True, "has_tables is True"
        assert ctx["layout_type"] in ("table", "mixed"), \
            f"layout_type is 'table' or 'mixed'; got '{ctx['layout_type']}'"
    finally:
        os.unlink(path)


def test_detect_layout_context_error_resilience():
    print("\n[detect_layout_context] error resilience (empty page)")
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    try:
        ctx = core.detect_layout_context(page)
        assert isinstance(ctx, dict), "returns dict on empty page"
        assert "layout_type" in ctx, "layout_type present"
    finally:
        doc.close()


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    """Direct-run entry point (pytest is the preferred runner)."""
    print("=" * 60)
    print("Week 7 Day 2 — Layout Detection Tests")
    print("=" * 60)

    tests = [
        test_detect_columns_single,
        test_detect_columns_two,
        test_get_text_rotation_normal,
        test_get_text_rotation_empty_span,
        test_detect_tables_no_lines,
        test_detect_tables_grid,
        test_get_reading_order_single,
        test_get_reading_order_two_column,
        test_detect_layout_context_single,
        test_detect_layout_context_two_column,
        test_detect_layout_context_with_rect,
        test_detect_layout_context_table,
        test_detect_layout_context_error_resilience,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception:
            print(f"  ✗  {t.__name__} raised an exception:")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed  "
          f"({passed}/{passed + failed})")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
