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


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_detect_columns_single():
    print("\n[detect_columns] single-column page")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            cols = core.detect_columns(page)
        _check("returns a list", isinstance(cols, list))
        _check("single column → 0 or 1 column rects", len(cols) <= 1,
               f"got {len(cols)}")
    finally:
        os.unlink(path)


def test_detect_columns_two():
    print("\n[detect_columns] two-column page")
    path = _make_two_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            cols = core.detect_columns(page)
        _check("returns a list", isinstance(cols, list))
        _check("detects 2 columns", len(cols) == 2, f"got {len(cols)}")
        if len(cols) == 2:
            _check("left col is left of right col", cols[0].x0 < cols[1].x0)
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
        _check("at least one span", len(spans) > 0)
        if spans:
            angle = core.get_text_rotation(spans[0])
            _check("returns int", isinstance(angle, int))
            _check("normal text is 0°", angle == 0, f"got {angle}")
    finally:
        os.unlink(path)


def test_get_text_rotation_empty_span():
    print("\n[get_text_rotation] span without 'dir' key → 0°")
    angle = core.get_text_rotation({})
    _check("returns 0 for missing dir", angle == 0, f"got {angle}")


def test_detect_tables_no_lines():
    print("\n[detect_tables] page without lines → empty list")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            tables = core.detect_tables(page)
        _check("returns list", isinstance(tables, list))
        _check("no tables on plain text page", len(tables) == 0, f"got {len(tables)}")
    finally:
        os.unlink(path)


def test_detect_tables_grid():
    print("\n[detect_tables] page with 3×3 grid")
    path = _make_table_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            tables = core.detect_tables(page)
        _check("returns list", isinstance(tables, list))
        _check("detects at least one table", len(tables) >= 1, f"got {len(tables)}")
        if tables:
            t = tables[0]
            _check("table has 'rect'", "rect" in t)
            _check("table has 'rows'", "rows" in t)
            _check("table has 'cols'", "cols" in t)
            _check("table has 'cells'", "cells" in t)
            _check("3 rows detected", t["rows"] == 3, f"got {t['rows']}")
            _check("3 cols detected", t["cols"] == 3, f"got {t['cols']}")
            _check("9 cells", len(t["cells"]) == 9, f"got {len(t['cells'])}")
    finally:
        os.unlink(path)


def test_get_reading_order_single():
    print("\n[get_reading_order] single-column → top-to-bottom")
    path = _make_single_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ordered = core.get_reading_order(page)
        _check("returns list", isinstance(ordered, list))
        _check("has blocks", len(ordered) > 0)
        # Verify top-to-bottom ordering
        ys = [b["bbox"][1] for b in ordered]
        _check("y-coordinates non-decreasing", ys == sorted(ys),
               f"out-of-order: {ys}")
    finally:
        os.unlink(path)


def test_get_reading_order_two_column():
    print("\n[get_reading_order] two-column → left column before right column")
    path = _make_two_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ordered = core.get_reading_order(page)
        _check("has blocks", len(ordered) > 0)
        # First block should be in left column (x0 < 250)
        if ordered:
            _check("first block is in left column",
                   ordered[0]["bbox"][0] < 250,
                   f"x0={ordered[0]['bbox'][0]:.1f}")
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
            _check(f"has key '{key}'", key in ctx)
        _check("layout_type is 'single_column'",
               ctx["layout_type"] == "single_column",
               f"got '{ctx['layout_type']}'")
        _check("dominant_rotation is 0", ctx["dominant_rotation"] == 0,
               f"got {ctx['dominant_rotation']}")
        _check("has_rotated_text is False", ctx["has_rotated_text"] is False)
    finally:
        os.unlink(path)


def test_detect_layout_context_two_column():
    print("\n[detect_layout_context] two-column page")
    path = _make_two_column_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ctx = core.detect_layout_context(page)
        _check("layout_type is 'multi_column'",
               ctx["layout_type"] == "multi_column",
               f"got '{ctx['layout_type']}'")
        _check("column_count is 2", ctx["column_count"] == 2,
               f"got {ctx['column_count']}")
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
        _check("column_index is 0 (left column)",
               ctx["column_index"] == 0,
               f"got {ctx['column_index']}")
    finally:
        os.unlink(path)


def test_detect_layout_context_table():
    print("\n[detect_layout_context] page with table")
    path = _make_table_pdf()
    try:
        with fitz.open(path) as doc:
            page = doc[0]
            ctx = core.detect_layout_context(page)
        _check("has_tables is True", ctx["has_tables"] is True)
        _check("layout_type is 'table' or 'mixed'",
               ctx["layout_type"] in ("table", "mixed"),
               f"got '{ctx['layout_type']}'")
    finally:
        os.unlink(path)


def test_detect_layout_context_error_resilience():
    print("\n[detect_layout_context] error resilience (empty page)")
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    try:
        ctx = core.detect_layout_context(page)
        _check("returns dict on empty page", isinstance(ctx, dict))
        _check("layout_type present", "layout_type" in ctx)
    finally:
        doc.close()


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
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
