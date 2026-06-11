#!/usr/bin/env python3
"""
generate_corpus.py — Creates the XCUITest PDF corpus for Marcedit.

Run once (or whenever cases change) to regenerate test PDFs and their manifests.
Each case lives in tests/ui_corpus/cases/<id>/ and contains:
  - input.pdf    (the test PDF)
  - manifest.json (click position, expected text, replacement, etc.)

Usage:
    python3 tests/ui_corpus/generate_corpus.py
"""

import json
import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF (fitz) not found. Install with: pip install pymupdf")
    sys.exit(1)

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "cases")


def _save(case_id: str, doc: fitz.Document, manifest: dict):
    case_dir = os.path.join(CORPUS_DIR, case_id)
    os.makedirs(case_dir, exist_ok=True)
    pdf_path = os.path.join(case_dir, "input.pdf")
    manifest_path = os.path.join(case_dir, "manifest.json")
    doc.save(pdf_path)
    doc.close()
    manifest["pdfPath"] = pdf_path
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  ✓ {case_id}: {pdf_path}")


# ---------------------------------------------------------------------------
# Case 001 — Simple word replacement
# One text block "Hello World" at a known position.
# ---------------------------------------------------------------------------
def case_001():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter

    # Insert text with a reliable system font so Marcedit can detect it
    page.insert_text((72, 720), "Hello World", fontsize=14, fontname="helv")
    page.insert_text((72, 695), "Second line of text here", fontsize=12, fontname="helv")
    page.insert_text((72, 670), "Third line for scrolling tests", fontsize=12, fontname="helv")

    # normalised click position within PDFViewer:
    # PDFViewer renders the page; we aim at the text y=720 from bottom-left.
    # In a 612×792 page:  normX ≈ 72/612 ≈ 0.12, normY from top ≈ (792-720)/792 ≈ 0.09
    manifest = {
        "id": "001_simple_word",
        "targetText": "Hello World",
        "clickNormX": 0.18,
        "clickNormY": 0.09,
        "replacement": "Hi there",
        "expectedOutputText": "Hi there",
        "expectedFont": None,
        "pageIndex": 0,
    }
    _save("001_simple_word", doc, manifest)


# ---------------------------------------------------------------------------
# Case 002 — Full-line replacement (longer text)
# ---------------------------------------------------------------------------
def case_002():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    page.insert_text((72, 720), "Sample text for editing", fontsize=12, fontname="helv")
    page.insert_text((72, 695), "Another paragraph line below", fontsize=12, fontname="helv")

    manifest = {
        "id": "002_full_line",
        "targetText": "Sample text for editing",
        "clickNormX": 0.25,
        "clickNormY": 0.09,
        "replacement": "New content here",
        "expectedOutputText": "New content here",
        "expectedFont": None,
        "pageIndex": 0,
    }
    _save("002_full_line", doc, manifest)


# ---------------------------------------------------------------------------
# Case 003 — Split text runs on the same visual line
# This specifically tests the joinedLineSelection() fix in InteractivePDFView.swift.
# Two separate insert_text() calls at the SAME y coordinate create two PDF text
# objects on the same visual line. Pre-fix: selectionForLine returned only "Hello "
# (truncated). Post-fix: joinedLineSelection() merges them into "Hello World!".
# ---------------------------------------------------------------------------
def case_003():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # TWO text objects at the same y=720, adjacent x positions — same visual line
    page.insert_text((72, 720), "Hello ", fontsize=14, fontname="helv")
    page.insert_text((106, 720), "World!", fontsize=14, fontname="helv")  # immediately after "Hello "

    page.insert_text((72, 690), "Normal single-object line", fontsize=12, fontname="helv")

    manifest = {
        "id": "003_split_runs",
        # The full joined text that should be selected on single/double-click
        "targetText": "Hello World!",
        # Click in the middle of "Hello " — the FIRST text object
        "clickNormX": 0.15,
        "clickNormY": 0.09,
        "replacement": "Joined text",
        "expectedOutputText": "Joined text",
        "expectedFont": None,
        "pageIndex": 0,
        # Extra field for SelectionAccuracyTests — what a truncated (broken) result looks like
        "truncatedText": "Hello ",
    }
    _save("003_split_runs", doc, manifest)


# ---------------------------------------------------------------------------
# Case 004 — Multi-page: edit on page 2
# ---------------------------------------------------------------------------
def case_004():
    doc = fitz.open()
    page1 = doc.new_page(width=612, height=792)
    page1.insert_text((72, 720), "Page one content", fontsize=12, fontname="helv")

    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((72, 720), "Page two content", fontsize=12, fontname="helv")
    page2.insert_text((72, 695), "More text on second page", fontsize=12, fontname="helv")

    manifest = {
        "id": "004_multipage",
        "targetText": "Page two content",
        "clickNormX": 0.20,
        "clickNormY": 0.09,
        "replacement": "Edited page two",
        "expectedOutputText": "Edited page two",
        "expectedFont": None,
        "pageIndex": 1,  # 0-based page index for page 2
    }
    _save("004_multipage", doc, manifest)


# ---------------------------------------------------------------------------
# Case 005 — Font preservation (Helvetica-Bold)
# After editing, the replacement text should use the same font family.
# ---------------------------------------------------------------------------
def case_005():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # Use built-in bold font
    page.insert_text((72, 720), "Bold Sample Text", fontsize=14, fontname="hebo")  # Helvetica-Bold
    page.insert_text((72, 695), "Regular text below", fontsize=12, fontname="helv")

    manifest = {
        "id": "005_font_preservation",
        "targetText": "Bold Sample Text",
        "clickNormX": 0.22,
        "clickNormY": 0.09,
        "replacement": "New Bold Text",
        "expectedOutputText": "New Bold Text",
        "expectedFont": "Helvetica-Bold",
        "pageIndex": 0,
    }
    _save("005_font_preservation", doc, manifest)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"Generating XCUITest corpus in: {CORPUS_DIR}")
    case_001()
    case_002()
    case_003()
    case_004()
    case_005()
    print("\nDone. Run 'xcodebuild test -project MarceditApp.xcodeproj -scheme MarceditUITests -destination platform=macOS' to execute tests.")


if __name__ == "__main__":
    main()
