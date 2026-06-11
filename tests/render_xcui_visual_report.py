#!/usr/bin/env python3
"""Render XCUITest edit manifests into the stable visual report artifacts."""

from __future__ import annotations

import html
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz


REPORT_DIR = Path("/tmp/marcedit_visual_report")
DPI = 150
THRESHOLD = 8
CROP_PADDING = 80


def manifest_roots() -> list[Path]:
    home = Path.home()
    roots = [
        Path(tempfile.gettempdir()),
        Path("/tmp"),
        home / "Library" / "Caches" / "MarceditUITests",
    ]
    roots.extend(
        (home / "Library" / "Containers").glob("*/Data/Library/Caches/MarceditUITests")
    )
    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def find_manifests() -> list[Path]:
    manifests: list[Path] = []
    for root in manifest_roots():
        manifests.extend(root.glob("marcedit_uitest_*/xcui_case_result.json"))
    return sorted(set(manifests))


def render_page(pdf_path: Path, page_index: int, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72.0, DPI / 72.0))
        pix.save(output_path)


def diff_bbox(before_path: Path, after_path: Path) -> list[int] | None:
    pix1 = fitz.Pixmap(before_path)
    pix2 = fitz.Pixmap(after_path)
    if pix1.width != pix2.width or pix1.height != pix2.height:
        raise ValueError("Image dimensions differ")

    width, height, channels = pix1.width, pix1.height, pix1.n
    samples1, samples2 = pix1.samples, pix2.samples
    stride = width * channels
    min_x, min_y = width, height
    max_x, max_y = -1, -1

    for y in range(height):
        row_offset = y * stride
        for x in range(width):
            offset = row_offset + x * channels
            delta = max(
                abs(samples1[offset + c] - samples2[offset + c])
                for c in range(min(channels, 3))
            )
            if delta > THRESHOLD:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < 0:
        return None
    return [min_x, min_y, max_x, max_y]


def crop_pair(
    before_path: Path,
    after_path: Path,
    crop_before_path: Path,
    crop_after_path: Path,
    bbox: list[int] | None,
) -> list[int]:
    before_pix = fitz.Pixmap(before_path)
    width, height = before_pix.width, before_pix.height

    if bbox is None:
        x0 = max(0, width // 4)
        y0 = max(0, height // 4)
        x1 = min(width - 1, width * 3 // 4)
        y1 = min(height - 1, height * 3 // 4)
    else:
        x0 = max(0, bbox[0] - CROP_PADDING)
        y0 = max(0, bbox[1] - CROP_PADDING)
        x1 = min(width - 1, bbox[2] + CROP_PADDING)
        y1 = min(height - 1, bbox[3] + CROP_PADDING)

    box = (x0, y0, x1 + 1, y1 + 1)
    for src, dst in [(before_path, crop_before_path), (after_path, crop_after_path)]:
        dst.parent.mkdir(parents=True, exist_ok=True)
        fitz.Pixmap(src).pil_image().crop(box).save(dst)

    return [x0, y0, x1, y1]


def render_case(manifest_path: Path) -> tuple[dict[str, Any], str | None]:
    data = json.loads(manifest_path.read_text())
    case_id = data["caseID"]
    case_dir = REPORT_DIR / case_id

    entry: dict[str, Any] = {
        "testName": data.get("testName", "testVisualReport_AllCases"),
        "caseID": case_id,
        "page": data["page"],
        "targetText": data["targetText"],
        "replacement": data["replacement"],
        "expectedOutputText": data.get("expectedOutputText", ""),
        "expectedFont": data.get("expectedFont"),
        "beforePNG": "",
        "afterPNG": "",
        "cropBeforePNG": None,
        "cropAfterPNG": None,
        "diffBBox": None,
        "cropBBox": None,
        "status": data.get("status", "failed"),
        "message": data.get("message", ""),
    }

    if entry["status"] != "success":
        return entry, None

    try:
        input_pdf = Path(data["inputPDF"])
        output_pdf = Path(data["outputPDF"])
        before_png = case_dir / f"{case_id}_before.png"
        after_png = case_dir / f"{case_id}_after.png"
        crop_before = case_dir / f"{case_id}_crop_before.png"
        crop_after = case_dir / f"{case_id}_crop_after.png"

        render_page(input_pdf, int(data["page"]), before_png)
        render_page(output_pdf, int(data["page"]), after_png)
        bbox = diff_bbox(before_png, after_png)
        crop_bbox = crop_pair(before_png, after_png, crop_before, crop_after, bbox)

        entry.update(
            {
                "beforePNG": str(before_png),
                "afterPNG": str(after_png),
                "cropBeforePNG": str(crop_before),
                "cropAfterPNG": str(crop_after),
                "diffBBox": bbox,
                "cropBBox": crop_bbox,
            }
        )
        return entry, None
    except Exception as exc:  # noqa: BLE001 - report generation should preserve context.
        entry["status"] = "failed"
        entry["message"] = f"visual render failed: {exc}"
        return entry, f"{case_id}: {exc}"


def rel_img(path: str, max_width: int) -> str:
    if not path:
        return "(not generated)"
    image_path = Path(path)
    try:
        src = image_path.relative_to(REPORT_DIR)
    except ValueError:
        src = image_path
    return f'<img src="{html.escape(str(src))}" style="max-width:{max_width}px">'


def write_json(entries: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "visual_report.json").write_text(
        json.dumps(entries, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_html(entries: list[dict[str, Any]]) -> None:
    success_count = sum(1 for entry in entries if entry["status"] == "success")
    failed_count = sum(1 for entry in entries if entry["status"] == "failed")
    skipped_count = sum(1 for entry in entries if entry["status"] == "skipped")

    cards = []
    for entry in entries:
        ok = entry["status"] == "success"
        bg = "#d4edda" if ok else "#f8d7da"
        status_color = "green" if ok else "red"
        message = (
            f"<br><i>{html.escape(entry['message'])}</i>" if entry.get("message") else ""
        )
        cards.append(
            f"""
            <div style="background:{bg};margin:12px 0;padding:12px;border-radius:6px">
              <b>{html.escape(entry['testName'])}</b> - case {html.escape(entry['caseID'])}
              - page {entry['page']}
              - <span style="color:{status_color}">{html.escape(entry['status'].upper())}</span><br>
              <code>{html.escape(entry['targetText'][:60])}</code>
              -> <code>{html.escape(entry['replacement'][:60])}</code>
              {message}
              <br><small>Diff bbox: {html.escape(str(entry.get('diffBBox') or 'none'))}</small>
              <table style="margin-top:8px"><tr>
                <td style="padding-right:12px;vertical-align:top"><b>Before</b><br>{rel_img(entry.get('beforePNG', ''), 420)}</td>
                <td style="padding-right:12px;vertical-align:top"><b>After</b><br>{rel_img(entry.get('afterPNG', ''), 420)}</td>
                <td style="vertical-align:top"><b>Crop (Before -> After)</b><br>
                  {rel_img(entry.get('cropBeforePNG') or '', 300)}<br>
                  {rel_img(entry.get('cropAfterPNG') or '', 300)}
                </td>
              </tr></table>
            </div>
            """
        )

    body = "\n".join(cards)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Marcedit XCUITest Visual Report</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; }}
  table {{ border-collapse: collapse; }}
  code {{ background: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-size: 12px; }}
  img {{ border: 1px solid #ccc; }}
</style>
</head>
<body>
<h1>Marcedit - XCUITest Visual Report</h1>
<p>Generated: {html.escape(generated)}</p>
<h2>Summary</h2>
<p>Total: {len(entries)} &nbsp;|&nbsp;
   OK {success_count} succeeded &nbsp;|&nbsp;
   FAIL {failed_count} failed &nbsp;|&nbsp;
   SKIP {skipped_count} skipped</p>
{body}
</body>
</html>
"""
    (REPORT_DIR / "visual_report.html").write_text(html_doc, encoding="utf-8")


def main() -> int:
    manifests = find_manifests()
    if not manifests:
        print("[xcui-render] No XCUITest case manifests found.")
        return 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    render_errors: list[str] = []
    for manifest in manifests:
        entry, error = render_case(manifest)
        entries.append(entry)
        if error:
            render_errors.append(error)

    entries.sort(key=lambda entry: entry["caseID"])
    write_json(entries)
    write_html(entries)

    print(f"[xcui-render] Wrote {len(entries)} entries to {REPORT_DIR}")
    if render_errors:
        print("[xcui-render] Render errors:")
        for error in render_errors:
            print(f"  - {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
