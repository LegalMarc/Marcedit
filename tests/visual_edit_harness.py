"""
Visual edit harness — real-world PDF smoke test.

For each PDF in the sample-files directory:
  1. Extract up to 10 editable text spans (single-line, no garbage chars)
  2. Generate a realistic substitution (same-word swap, shorter, longer)
  3. Apply it via replace_text_in_pdf()
  4. Render before/after page at 150 DPI → PNG
  5. Save a tight crop of the changed region for visual review
  6. Record outcome (success / skip / fail) and collision info
  7. Write a self-contained HTML report with side-by-side thumbnails + crops

Run:
    python3 tests/visual_edit_harness.py          # full run
    python3 tests/visual_edit_harness.py --with-review  # merge review_results.json into HTML
Output:
    tests/visual_edit_harness_report/report.html
    tests/visual_edit_harness_report/review_queue.json
    tests/visual_edit_harness_report/review_results.json  (written externally, merged with --with-review)
"""

import os
import sys
import json
import time
import random
import shutil
import tempfile
import textwrap
import struct
import zlib
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SITE = _PROJECT_ROOT / "Sources" / "Marcedit" / "python_site"
if str(_SITE) not in sys.path:
    sys.path.insert(0, str(_SITE))

import fitz  # noqa: E402
from editor_pkg.core import replace_text_in_pdf  # noqa: E402

# ── configuration ─────────────────────────────────────────────────────────────
SAMPLE_DIR = _PROJECT_ROOT / "ignored-resources" / "sample-files-marcedit"
OUT_DIR    = _PROJECT_ROOT / "tests" / "visual_edit_harness_report"
EDITS_PER_PDF = 10
RENDER_DPI    = 150
RANDOM_SEED   = 42
CROP_PADDING  = 80   # px at 150 DPI around the changed region

random.seed(RANDOM_SEED)

# Substitution word bank — varied lengths so we exercise both shrink and grow
_WORD_BANK = [
    "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Acme", "Corp",
    "Inc", "LLC", "Holdings", "Group", "Services", "Solutions",
    "January", "February", "March", "April", "2024", "2025", "2026",
    "One", "Two", "Three", "Four", "Five",
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "New York", "Chicago", "Boston", "Dallas", "Miami",
    "AMENDED", "REVISED", "UPDATED", "APPROVED", "PENDING",
]

# ── helpers ───────────────────────────────────────────────────────────────────

def _is_editable_span(text: str) -> bool:
    """Return True if the span is a good edit candidate."""
    t = text.strip()
    if len(t) < 3 or len(t) > 60:
        return False
    # No garbage Unicode
    if any(ord(c) >= 0xFFFD for c in t):
        return False
    # Must have at least one alphabetic character
    if not any(c.isalpha() for c in t):
        return False
    # Avoid things that look like page numbers, footnotes, single chars
    if len(t) <= 2:
        return False
    return True


def _make_substitution(original: str) -> str:
    """Create a plausible replacement string for *original*."""
    words = original.strip().split()
    if not words:
        return random.choice(_WORD_BANK)

    if len(words) == 1:
        # Single word: swap the whole thing
        candidate = random.choice(_WORD_BANK)
        # Try to preserve rough case style
        if original.isupper():
            return candidate.upper()
        if original[0].isupper():
            return candidate.capitalize()
        return candidate.lower()
    else:
        # Multi-word: replace one random word
        idx = random.randint(0, len(words) - 1)
        replacement_word = random.choice(_WORD_BANK)
        if words[idx].isupper():
            replacement_word = replacement_word.upper()
        elif words[idx][0].isupper():
            replacement_word = replacement_word.capitalize()
        else:
            replacement_word = replacement_word.lower()
        words[idx] = replacement_word
        return " ".join(words)


def _render_page_png(pdf_path: str, page_num: int, out_path: str, dpi: int = 150) -> bool:
    """Render *page_num* (0-based) of *pdf_path* to a PNG at *dpi*."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        pix.save(out_path)
        doc.close()
        return True
    except Exception as e:
        print(f"    [render] ERROR: {e}")
        return False


def _collect_edit_candidates(pdf_path: str, max_candidates: int = 30):
    """
    Return a list of (page_num_1based, span_text) candidates from the PDF.
    Picks single-line spans from various pages.
    """
    candidates = []
    try:
        doc = fitz.open(pdf_path)
        pages = list(range(len(doc)))
        random.shuffle(pages)
        for pg_idx in pages:
            if len(candidates) >= max_candidates:
                break
            page = doc[pg_idx]
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if _is_editable_span(text):
                            candidates.append((pg_idx + 1, text.strip()))
        doc.close()
    except Exception as e:
        print(f"  [collect] ERROR: {e}")
    return candidates


# ── PNG pixel-diff helpers ────────────────────────────────────────────────────

def _read_png_pixels(path: str):
    """
    Minimal PNG decoder — returns (width, height, pixels_rgba_flat) without
    depending on PIL/Pillow. Handles only 8-bit RGB/RGBA deflate PNGs which is
    what fitz produces.
    """
    with open(path, "rb") as f:
        data = f.read()

    # Collect all IDAT chunks
    pos = 8  # skip PNG magic
    width = height = bit_depth = color_type = 0
    idat_chunks = []

    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]
        tag = data[pos+4:pos+8]
        chunk_data = data[pos+8:pos+8+length]
        if tag == b"IHDR":
            width, height = struct.unpack(">II", chunk_data[:8])
            bit_depth, color_type = chunk_data[8], chunk_data[9]
        elif tag == b"IDAT":
            idat_chunks.append(chunk_data)
        elif tag == b"IEND":
            break
        pos += 12 + length

    raw = zlib.decompress(b"".join(idat_chunks))

    # channel count
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 3)
    stride = width * ch + 1  # +1 for filter byte per row

    pixels = []  # flat RGBA list
    for y in range(height):
        filt = raw[y * stride]
        row_raw = list(raw[y * stride + 1: y * stride + 1 + width * ch])

        # Undo filter (only None=0 and Sub=1 and Up=2 and Average=3 and Paeth=4)
        if y == 0:
            prev = [0] * (width * ch)
        if filt == 1:   # Sub
            for i in range(ch, len(row_raw)):
                row_raw[i] = (row_raw[i] + row_raw[i - ch]) & 0xFF
        elif filt == 2: # Up
            for i in range(len(row_raw)):
                row_raw[i] = (row_raw[i] + prev[i]) & 0xFF
        elif filt == 3: # Average
            for i in range(len(row_raw)):
                a = row_raw[i - ch] if i >= ch else 0
                b = prev[i]
                row_raw[i] = (row_raw[i] + (a + b) // 2) & 0xFF
        elif filt == 4: # Paeth
            def paeth(a, b, c):
                p = a + b - c
                pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                return a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            for i in range(len(row_raw)):
                a = row_raw[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                row_raw[i] = (row_raw[i] + paeth(a, b, c)) & 0xFF

        prev = row_raw

        for x in range(width):
            r = row_raw[x * ch]
            g = row_raw[x * ch + 1] if ch >= 3 else r
            b_val = row_raw[x * ch + 2] if ch >= 3 else r
            a = row_raw[x * ch + 3] if ch == 4 else 255
            pixels.append((r, g, b_val, a))

    return width, height, pixels


def _compute_diff_bbox(before_path: str, after_path: str, threshold: int = 8):
    """
    Compare two same-size PNGs. Return bounding box (x0,y0,x1,y1) of all
    pixels that differ by more than *threshold* in any channel, or None if
    images are identical. Uses only stdlib (struct + zlib).
    """
    try:
        w1, h1, px1 = _read_png_pixels(before_path)
        w2, h2, px2 = _read_png_pixels(after_path)
    except Exception as e:
        print(f"    [diff] Could not read PNGs: {e}")
        return None

    if w1 != w2 or h1 != h2:
        return None

    min_x, min_y = w1, h1
    max_x, max_y = -1, -1

    for idx in range(w1 * h1):
        r1, g1, b1, _ = px1[idx]
        r2, g2, b2, _ = px2[idx]
        if max(abs(r1-r2), abs(g1-g2), abs(b1-b2)) > threshold:
            x = idx % w1
            y = idx // w1
            if x < min_x: min_x = x
            if y < min_y: min_y = y
            if x > max_x: max_x = x
            if y > max_y: max_y = y

    if max_x < 0:
        return None  # no difference
    return (min_x, min_y, max_x, max_y)


def _save_crop(before_path: str, after_path: str,
               crop_before_path: str, crop_after_path: str,
               padding: int = CROP_PADDING) -> tuple | None:
    """
    Compute the diff bounding box, expand by *padding* px, and save crops of
    both before and after to the given paths.  Returns (x0,y0,x1,y1) of the
    crop region or None on failure.
    """
    bbox = _compute_diff_bbox(before_path, after_path)

    try:
        w, h, _ = _read_png_pixels(before_path)
    except Exception:
        return None

    if bbox is None:
        # No visible diff — crop the full page as a fallback
        bbox = (0, 0, w - 1, h - 1)

    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(w - 1, x1 + padding)
    y1 = min(h - 1, y1 + padding)

    # Use fitz to do the actual crop (avoids a PIL dependency)
    clip = fitz.IRect(x0, y0, x1 + 1, y1 + 1)
    for src, dst in [(before_path, crop_before_path), (after_path, crop_after_path)]:
        try:
            pix = fitz.Pixmap(src)
            cropped = fitz.Pixmap(pix.colorspace, clip, pix.alpha)
            cropped.copy(pix, clip)
            cropped.save(dst)
        except Exception as e:
            print(f"    [crop] ERROR cropping {src}: {e}")
            return None

    return (x0, y0, x1, y1)


# ── per-PDF processing ────────────────────────────────────────────────────────

def process_pdf(pdf_path: Path, out_dir: Path) -> dict:
    """
    Run up to EDITS_PER_PDF edits on *pdf_path* and return a results dict.
    """
    pdf_name = pdf_path.name
    pdf_slug = pdf_path.stem.replace(" ", "_")[:40]
    pdf_out  = out_dir / pdf_slug
    pdf_out.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"PDF: {pdf_name}")

    results = {
        "pdf": pdf_name,
        "path": str(pdf_path),
        "edits": [],
        "summary": {"success": 0, "failed": 0, "skipped": 0},
    }

    # Collect candidates
    candidates = _collect_edit_candidates(str(pdf_path), max_candidates=50)
    if not candidates:
        print("  No editable spans found — skipping")
        results["summary"]["skipped"] = EDITS_PER_PDF
        return results

    # Deduplicate and sample
    seen = set()
    unique = []
    for pg, txt in candidates:
        key = (pg, txt[:30])
        if key not in seen:
            seen.add(key)
            unique.append((pg, txt))

    random.shuffle(unique)
    selected = unique[:EDITS_PER_PDF]

    for edit_idx, (page_num, target_text) in enumerate(selected):
        replacement = _make_substitution(target_text)
        edit_label  = f"edit_{edit_idx+1:02d}"

        before_png      = str(pdf_out / f"{edit_label}_before.png")
        after_png       = str(pdf_out / f"{edit_label}_after.png")
        crop_before_png = str(pdf_out / f"{edit_label}_crop_before.png")
        crop_after_png  = str(pdf_out / f"{edit_label}_crop_after.png")

        print(f"  [{edit_idx+1:2d}/{len(selected)}] p{page_num}: "
              f"{repr(target_text[:35])} → {repr(replacement[:35])}")

        # Render before
        _render_page_png(str(pdf_path), page_num - 1, before_png)

        # Apply edit
        fd, tmp_out = tempfile.mkstemp(suffix=".pdf", prefix="marcedit_vis_")
        os.close(fd)
        t0 = time.perf_counter()
        try:
            result = replace_text_in_pdf(
                input_path=str(pdf_path),
                output_path=tmp_out,
                target_text=target_text,
                replacement_text=replacement,
                page_number=page_num,
            )
        except Exception as exc:
            result = {"success": False, "message": str(exc)}
        elapsed = time.perf_counter() - t0

        success   = result.get("success", False)
        message   = result.get("message", "")
        debug_log = result.get("debug_log", [])

        crop_bbox = None
        if success:
            _render_page_png(tmp_out, page_num - 1, after_png)
            status = "success"
            results["summary"]["success"] += 1
            print(f"       ✓ {elapsed*1000:.0f}ms")
            # Save diff crop
            crop_bbox = _save_crop(before_png, after_png, crop_before_png, crop_after_png)
            if crop_bbox:
                print(f"         crop: {crop_bbox}")
        else:
            # Copy before as placeholder so the report still shows something
            shutil.copy2(before_png, after_png)
            shutil.copy2(before_png, crop_before_png)
            shutil.copy2(before_png, crop_after_png)
            status = "failed"
            results["summary"]["failed"] += 1
            print(f"       ✗ {message[:80]}")

        # Clean up tmp
        try:
            os.unlink(tmp_out)
        except OSError:
            pass

        results["edits"].append({
            "index":            edit_idx + 1,
            "page":             page_num,
            "target":           target_text,
            "replacement":      replacement,
            "status":           status,
            "message":          message,
            "elapsed_ms":       round(elapsed * 1000, 1),
            "debug_log":        debug_log[-5:] if debug_log else [],
            "before_png":       before_png,
            "after_png":        after_png,
            "crop_before_png":  crop_before_png,
            "crop_after_png":   crop_after_png,
            "crop_bbox":        list(crop_bbox) if crop_bbox else None,
            "review_result":    None,
        })

    pct = 100 * results["summary"]["success"] / max(len(selected), 1)
    print(f"  → {results['summary']['success']}/{len(selected)} succeeded ({pct:.0f}%)")
    return results


# ── review queue ──────────────────────────────────────────────────────────────

def _write_review_queue(all_results: list, out_dir: Path, review_results: dict):
    """
    Write review_queue.json — one entry per successful edit, with paths to
    crops and metadata. Merges any existing review scores from *review_results*.
    """
    queue = []
    for pr in all_results:
        for e in pr["edits"]:
            if e["status"] != "success":
                continue
            rr = review_results.get(_edit_key(pr["pdf"], e["index"]))
            # Make paths relative to out_dir for portability
            def rel(p):
                try:
                    return os.path.relpath(p, out_dir)
                except Exception:
                    return p

            queue.append({
                "pdf":          pr["pdf"],
                "edit_index":   e["index"],
                "page":         e["page"],
                "target":       e["target"],
                "replacement":  e["replacement"],
                "elapsed_ms":   e["elapsed_ms"],
                "crop_bbox":    e.get("crop_bbox"),
                "crop_before":  rel(e.get("crop_before_png", e["before_png"])),
                "crop_after":   rel(e.get("crop_after_png",  e["after_png"])),
                "full_before":  rel(e["before_png"]),
                "full_after":   rel(e["after_png"]),
                "review_result": rr,
            })

    path = out_dir / "review_queue.json"
    path.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  review_queue.json: {len(queue)} entries → {path}")
    return queue


def _edit_key(pdf: str, index: int) -> str:
    return f"{pdf}::{index}"


# ── HTML report ───────────────────────────────────────────────────────────────

def _img_tag(path: str, base: Path, max_width: int = 420) -> str:
    try:
        rel = os.path.relpath(path, base)
        return f'<img src="{rel}" style="max-width:{max_width}px;border:1px solid #ccc">'
    except Exception:
        return "(no image)"


_REVIEW_BADGE = {
    None:    '<span style="background:#aaa;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px">⏳ Pending</span>',
    "pass":  '<span style="background:#28a745;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px">✅ Pass</span>',
    "warn":  '<span style="background:#ffc107;color:#000;padding:2px 6px;border-radius:3px;font-size:11px">⚠️ Warn</span>',
    "fail":  '<span style="background:#dc3545;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px">❌ Fail</span>',
}


def build_report(all_results: list, out_dir: Path, review_results: dict = None) -> Path:
    review_results = review_results or {}
    report_path = out_dir / "report.html"

    total_ok   = sum(r["summary"]["success"] for r in all_results)
    total_fail = sum(r["summary"]["failed"]  for r in all_results)
    total_skip = sum(r["summary"]["skipped"] for r in all_results)
    total      = total_ok + total_fail + total_skip

    rows = []
    for pr in all_results:
        pdf_name = pr["pdf"]
        ok   = pr["summary"]["success"]
        fail = pr["summary"]["failed"]
        colour = "#d4edda" if fail == 0 else ("#fff3cd" if ok > fail else "#f8d7da")
        rows.append(f'<tr style="background:{colour}">'
                    f'<td><b>{pdf_name}</b></td>'
                    f'<td style="text-align:center">{ok}</td>'
                    f'<td style="text-align:center">{fail}</td>'
                    f'<td style="text-align:center">{ok+fail}</td></tr>')

    edit_sections = []
    for pr in all_results:
        edits_html = []
        for e in pr["edits"]:
            bg = "#d4edda" if e["status"] == "success" else "#f8d7da"
            rr_key = _edit_key(pr["pdf"], e["index"])
            rr = review_results.get(rr_key)
            review_badge = _REVIEW_BADGE.get(rr.get("grade") if rr else None,
                                             _REVIEW_BADGE[None])
            debug = ""
            if e["status"] != "success" and e["debug_log"]:
                lines = "<br>".join(textwrap.shorten(l, 120) for l in e["debug_log"])
                debug = f'<p style="font-size:11px;color:#666">{lines}</p>'

            # Override card background with review grade
            if rr:
                grade = rr.get("grade")
                if grade == "warn":
                    bg = "#fff3cd"
                elif grade == "fail":
                    bg = "#f8d7da"

            before_img = _img_tag(e["before_png"], out_dir)
            after_img  = _img_tag(e["after_png"],  out_dir)

            # Crop images (smaller) — fall back to full page if crops not saved yet
            crop_before_img = _img_tag(e.get("crop_before_png") or e["before_png"], out_dir, 300)
            crop_after_img  = _img_tag(e.get("crop_after_png")  or e["after_png"],  out_dir, 300)

            review_notes_html = ""
            if rr and rr.get("notes"):
                review_notes_html = f'<p style="font-size:12px;color:#333;margin-top:4px"><b>Review notes:</b> {rr["notes"]}</p>'

            edits_html.append(f"""
<div style="background:{bg};margin:8px 0;padding:8px;border-radius:4px">
  <b>Edit {e['index']}</b> — page {e['page']} — {e['elapsed_ms']} ms
  — <span style="color:{'green' if e['status']=='success' else 'red'}">{e['status'].upper()}</span>
  &nbsp; {review_badge}<br>
  <code>{e['target'][:60]}</code> → <code>{e['replacement'][:60]}</code><br>
  {f"<i>{e['message'][:120]}</i>" if e['message'] else ""}
  {debug}
  {review_notes_html}
  <table style="margin-top:6px"><tr>
    <td style="padding-right:12px;vertical-align:top"><b>Before</b><br>{before_img}</td>
    <td style="padding-right:12px;vertical-align:top"><b>After</b><br>{after_img}</td>
    <td style="vertical-align:top"><b>Crop (Before → After)</b><br>
      {crop_before_img}<br>{crop_after_img}
    </td>
  </tr></table>
</div>""")

        edit_sections.append(f"""
<h2 style="margin-top:40px">{pr['pdf']}</h2>
<p>✓ {pr['summary']['success']} succeeded &nbsp; ✗ {pr['summary']['failed']} failed</p>
{''.join(edits_html)}""")

    with_review_note = ""
    if review_results:
        reviewed = len(review_results)
        passes = sum(1 for r in review_results.values() if r.get("grade") == "pass")
        warns  = sum(1 for r in review_results.values() if r.get("grade") == "warn")
        fails  = sum(1 for r in review_results.values() if r.get("grade") == "fail")
        with_review_note = (
            f'<p style="background:#e8f4fd;padding:8px;border-radius:4px">'
            f'<b>Visual review:</b> {reviewed} edits reviewed — '
            f'✅ {passes} pass &nbsp; ⚠️ {warns} warn &nbsp; ❌ {fails} fail</p>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Marcedit Visual Edit Harness</title>
<style>
  body {{font-family:sans-serif;max-width:1400px;margin:0 auto;padding:20px}}
  table {{border-collapse:collapse;width:100%}}
  th,td {{border:1px solid #ddd;padding:6px 10px;text-align:left}}
  th {{background:#f0f0f0}}
  code {{background:#f5f5f5;padding:2px 4px;border-radius:3px;font-size:12px}}
</style>
</head>
<body>
<h1>Marcedit — Visual Edit Harness Report</h1>
<p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp;
   Seed: {RANDOM_SEED} &nbsp;|&nbsp;
   DPI: {RENDER_DPI} &nbsp;|&nbsp;
   Edits per PDF: {EDITS_PER_PDF}</p>

{with_review_note}

<h2>Summary</h2>
<p>Total edits: {total} &nbsp;|&nbsp;
   ✓ {total_ok} succeeded &nbsp;|&nbsp;
   ✗ {total_fail} failed &nbsp;|&nbsp;
   — {total_skip} skipped</p>
<table>
<tr><th>PDF</th><th>Success</th><th>Failed</th><th>Total</th></tr>
{''.join(rows)}
</table>

{''.join(edit_sections)}
</body>
</html>"""

    report_path.write_text(html, encoding="utf-8")
    return report_path


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    with_review = "--with-review" in sys.argv

    if not SAMPLE_DIR.exists():
        print(f"ERROR: sample directory not found: {SAMPLE_DIR}")
        sys.exit(1)

    review_results = {}
    if with_review:
        rr_path = OUT_DIR / "review_results.json"
        if rr_path.exists():
            review_results = json.loads(rr_path.read_text(encoding="utf-8"))
            print(f"Loaded {len(review_results)} review results from {rr_path}")
        else:
            print(f"WARNING: --with-review specified but {rr_path} not found")

    pdfs = sorted(SAMPLE_DIR.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {SAMPLE_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # If --with-review only, reload existing results.json and skip re-running edits
    if with_review:
        json_path = OUT_DIR / "results.json"
        if json_path.exists():
            all_results = json.loads(json_path.read_text(encoding="utf-8"))
            print("Re-using existing results.json (not re-running edits)")
        else:
            print("ERROR: results.json not found; run without --with-review first")
            sys.exit(1)
    else:
        all_results = []
        for pdf_path in pdfs:
            results = process_pdf(pdf_path, OUT_DIR)
            all_results.append(results)

        # Save JSON summary
        json_path = OUT_DIR / "results.json"
        json_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")

    # Write review queue
    _write_review_queue(all_results, OUT_DIR, review_results)

    # Build HTML report
    report = build_report(all_results, OUT_DIR, review_results)

    print(f"\n{'='*60}")
    total_ok   = sum(r["summary"]["success"] for r in all_results)
    total_fail = sum(r["summary"]["failed"]  for r in all_results)
    total      = total_ok + total_fail
    print(f"TOTAL: {total_ok}/{total} succeeded ({100*total_ok//max(total,1)}%)")
    print(f"Report: {report}")
    print(f"Review queue: {OUT_DIR / 'review_queue.json'}")

    # Print all failures for quick triage
    print("\n── Failures ──────────────────────────────────────────")
    any_fail = False
    for pr in all_results:
        for e in pr["edits"]:
            if e["status"] != "success":
                any_fail = True
                print(f"  {pr['pdf'][:40]}  p{e['page']}: {repr(e['target'][:40])}")
                print(f"    → {e['message'][:100]}")
                if e["debug_log"]:
                    print(f"    debug: {e['debug_log'][-1][:100]}")
    if not any_fail:
        print("  (none)")


if __name__ == "__main__":
    main()
