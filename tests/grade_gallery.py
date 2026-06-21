"""
grade_gallery.py — worst-first visual gallery of graded edits.

Reads the visual harness output plus the agent-produced grades and emits a
single self-contained HTML page that shows FAILs first (grouped by defect),
then WARNs, then a collapsed PASS summary. Each card shows the before→after
crop side by side with the target→replacement and the grader's reason.

Inputs (in tests/visual_edit_harness_report/):
    review_queue.json     — crop paths + metadata (written by visual_edit_harness.py)
    review_results.json   — {"<pdf>::<index>": {grade, defect, notes, ...}}

Output:
    tests/visual_edit_harness_report/gallery.html

Run:
    ./.venv311/bin/python tests/grade_gallery.py
"""
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent / "visual_edit_harness_report"

GRADE_ORDER = {"fail": 0, "warn": 1, "pass": 2}
BADGE = {
    "pass": ('#1a7f37', '#fff', '✅ PASS'),
    "warn": ('#9a6700', '#fff', '⚠️ WARN'),
    "fail": ('#cf222e', '#fff', '❌ FAIL'),
}
DEFECT_BLURB = {
    "overflow_collision": "Wider replacement runs into neighbouring text / column / border",
    "font_mismatch":      "Replacement rendered in a different font, weight, or style",
    "color_mismatch":     "Replacement rendered in a different colour than its context",
    "ghost_artifact":     "Leftover original ink — strike-through, underline, double-print",
    "leftover_gap":       "Shorter replacement left a visible blank gap",
    "dropped_glyph":      "A character (€, curly quote, accent…) was silently dropped",
    "baseline_misalign":  "Replacement sits off the baseline or at the wrong size",
    "fragment_edit":      "Replacement injected mid-word, producing a nonsense token",
    "other":              "Other visible defect (see note)",
    "none":               "No defect",
}


def _img(path_rel, max_w=360):
    return (f'<img src="{path_rel}" loading="lazy" '
            f'style="max-width:{max_w}px;border:1px solid #d0d7de;border-radius:4px;background:#fff">')


def main():
    queue = json.loads((OUT / "review_queue.json").read_text())
    review = json.loads((OUT / "review_results.json").read_text())

    rows = []
    for q in queue:
        key = f"{q['pdf']}::{q['edit_index']}"
        rr = review.get(key, {"grade": "pass", "defect": "none", "notes": ""})
        rows.append({**q, **rr})

    rows.sort(key=lambda r: (GRADE_ORDER.get(r["grade"], 9),
                             r.get("defect", "zzz"),
                             r["pdf"]))

    n = len(rows)
    counts = {"pass": 0, "warn": 0, "fail": 0}
    defect_counts = {}
    for r in rows:
        counts[r["grade"]] = counts.get(r["grade"], 0) + 1
        if r["grade"] == "fail":
            defect_counts[r["defect"]] = defect_counts.get(r["defect"], 0) + 1

    def card(r):
        fg, _, label = BADGE.get(r["grade"], BADGE["pass"])
        before = _img(r["crop_before"])
        after = _img(r["crop_after"])
        defect = r.get("defect", "none")
        note = r.get("notes", "")
        return f"""
<div class="card grade-{r['grade']}">
  <div class="hd">
    <span class="badge" style="background:{fg}">{label}</span>
    <span class="defect">{defect}</span>
    <span class="pdf">{r['pdf']}</span>
    <span class="pg">p{r['page']} · edit {r['edit_index']}</span>
  </div>
  <div class="txt"><code class="t">{r['target'][:70]}</code> <span class="arr">→</span> <code class="r">{r['replacement'][:70]}</code></div>
  <div class="note">{note}</div>
  <table class="imgs"><tr>
    <td><div class="lbl">BEFORE</div>{before}</td>
    <td><div class="lbl">AFTER</div>{after}</td>
  </tr></table>
</div>"""

    sections = []
    # Fails grouped by defect, most common first
    fail_rows = [r for r in rows if r["grade"] == "fail"]
    if fail_rows:
        sections.append('<h2 class="sec fail">❌ Failures — a paying customer would reject these</h2>')
        for defect, _c in sorted(defect_counts.items(), key=lambda x: -x[1]):
            grp = [r for r in fail_rows if r["defect"] == defect]
            sections.append(f'<h3 class="grp">{defect} <span class="cnt">×{len(grp)}</span>'
                            f'<span class="blurb">{DEFECT_BLURB.get(defect, "")}</span></h3>')
            sections.extend(card(r) for r in grp)

    warn_rows = [r for r in rows if r["grade"] == "warn"]
    if warn_rows:
        sections.append('<h2 class="sec warn">⚠️ Warnings — minor cosmetic flaws</h2>')
        sections.extend(card(r) for r in warn_rows)

    pass_rows = [r for r in rows if r["grade"] == "pass"]
    if pass_rows:
        pass_list = "".join(
            f'<li><b>{r["pdf"][:40]}</b> p{r["page"]} e{r["edit_index"]}: '
            f'<code>{r["target"][:40]}</code> → <code>{r["replacement"][:40]}</code></li>'
            for r in pass_rows)
        sections.append(
            f'<h2 class="sec pass">✅ Passes ({len(pass_rows)})</h2>'
            f'<details><summary>Show {len(pass_rows)} clean edits</summary><ul class="passlist">{pass_list}</ul></details>')

    defect_summary = " · ".join(f"{d} ×{c}" for d, c in sorted(defect_counts.items(), key=lambda x: -x[1]))

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Marcedit — Edit Quality Gallery</title>
<style>
  body {{font-family:-apple-system,system-ui,sans-serif;max-width:840px;margin:0 auto;padding:24px;color:#1f2328;background:#fff}}
  h1 {{margin:0 0 4px}}
  .sub {{color:#656d76;margin:0 0 20px}}
  .scorebar {{display:flex;height:30px;border-radius:6px;overflow:hidden;margin:14px 0;font-size:13px;font-weight:600;color:#fff}}
  .scorebar div {{display:flex;align-items:center;justify-content:center}}
  .sb-fail {{background:#cf222e}} .sb-warn {{background:#9a6700}} .sb-pass {{background:#1a7f37}}
  h2.sec {{margin:34px 0 6px;padding-bottom:6px;border-bottom:2px solid #eaeef2}}
  h2.fail {{color:#cf222e}} h2.warn {{color:#9a6700}} h2.pass {{color:#1a7f37}}
  h3.grp {{margin:22px 0 8px;font-size:15px}}
  h3.grp .cnt {{color:#cf222e;margin-left:6px}}
  h3.grp .blurb {{display:block;font-weight:400;font-size:12px;color:#656d76;margin-top:2px}}
  .card {{border:1px solid #d0d7de;border-radius:8px;padding:12px 14px;margin:10px 0;background:#fafbfc}}
  .card.grade-fail {{border-left:4px solid #cf222e}}
  .card.grade-warn {{border-left:4px solid #9a6700}}
  .hd {{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;margin-bottom:6px}}
  .badge {{color:#fff;padding:2px 8px;border-radius:10px;font-weight:600}}
  .defect {{font-family:ui-monospace,monospace;background:#eaeef2;padding:2px 6px;border-radius:4px}}
  .pdf {{color:#1f2328;font-weight:600}}
  .pg {{color:#656d76;margin-left:auto}}
  .txt {{font-size:13px;margin:4px 0}}
  code.t {{background:#ffebe9;padding:1px 5px;border-radius:3px}}
  code.r {{background:#dafbe1;padding:1px 5px;border-radius:3px}}
  .arr {{color:#656d76;margin:0 4px}}
  .note {{font-size:12px;color:#444;font-style:italic;margin:4px 0 8px}}
  table.imgs {{border-collapse:collapse}} table.imgs td {{vertical-align:top;padding-right:14px}}
  .lbl {{font-size:10px;letter-spacing:.5px;color:#656d76;margin-bottom:3px}}
  details {{margin-top:8px}} summary {{cursor:pointer;color:#0969da}}
  .passlist {{columns:2;font-size:12px;color:#444}} .passlist code {{background:#f6f8fa;padding:0 3px}}
</style></head><body>
<h1>Marcedit — Edit Quality Gallery</h1>
<p class="sub">{n} edits · graded worst-first · before → after crops at 150 DPI</p>
<div class="scorebar">
  <div class="sb-fail" style="width:{100*counts['fail']//n}%">{counts['fail']} fail</div>
  <div class="sb-warn" style="width:{100*counts['warn']//n}%">{counts['warn']} warn</div>
  <div class="sb-pass" style="width:{100*counts['pass']//n}%">{counts['pass']} pass</div>
</div>
<p class="sub"><b>{counts['fail']} hard failures ({100*counts['fail']//n}%)</b> · {counts['warn']} warnings · {counts['pass']} clean &nbsp;|&nbsp; fail breakdown: {defect_summary}</p>
{''.join(sections)}
</body></html>"""

    out_path = OUT / "gallery.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"gallery → {out_path}  ({counts['fail']} fail / {counts['warn']} warn / {counts['pass']} pass)")


if __name__ == "__main__":
    main()
