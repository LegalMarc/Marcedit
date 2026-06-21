"""
grade_edits.py — the "judge" half of the visual loop.

Turns the harness output (review_queue.json) into per-PDF grading batches, then
fills in review_results.json with a pass/warn/fail grade + defect category for
every edit. Two grading backends:

  * API backend (automatic, CI-able): if ANTHROPIC_API_KEY is set and the
    `anthropic` SDK is importable, each before/after crop pair is sent to Claude
    and graded with structured output. Fully unattended.

  * Agent backend (fallback): otherwise we just emit the batch files + a manifest
    and exit 2, so an orchestrating Claude session can fan out one vision agent
    per batch (reading the same RUBRIC below) and write review_results.json.

Either way the schema is identical, so grade_gallery.py / report.html don't care
which backend produced the grades.

Run:
    ./.venv311/bin/python tests/grade_edits.py            # auto if key, else emit batches
    ./.venv311/bin/python tests/grade_edits.py --emit-only  # always just emit batches
"""
import json
import os
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "visual_edit_harness_report"

DEFECTS = [
    "overflow_collision", "font_mismatch", "color_mismatch", "leftover_gap",
    "dropped_glyph", "ghost_artifact", "baseline_misalign", "fragment_edit",
    "other", "none",
]

# Single source of truth for the grading rubric — shared by the API backend and
# the agent backend, so both judges apply identical criteria.
RUBRIC = """You are a meticulous visual-QA grader for a PDF text editor. The editor replaces \
text in-place; a good result looks like the text was ALWAYS there — same font, weight, size, \
color, baseline, and spacing, with no leftover ink, no collision with neighbouring text/borders, \
and no dropped characters.

You are given BEFORE and AFTER crops of the changed region, plus the original `target` text and \
the new `replacement` text. Grade the AFTER:
- "pass": clean; a user would not notice it was edited.
- "warn": minor cosmetic flaw (slight kerning/spacing, faint weight diff) but acceptable.
- "fail": obvious defect a paying customer would reject.

Defect category (closest match; "none" only if pass):
- overflow_collision: replacement overlaps/clips adjacent text, a cell border, or a column.
- font_mismatch: different font/weight/style than surrounding text.
- color_mismatch: different colour/shade than surrounding text.
- leftover_gap: shorter replacement left an obvious blank gap.
- dropped_glyph: a character is missing/blank (e.g. EUR sign, accented letter, omitted letters).
- ghost_artifact: leftover original ink — strike-through, underline, double-print, smudge.
- baseline_misalign: replacement sits off the baseline or at the wrong size.
- fragment_edit: replacement injected mid-word, producing a nonsense token.
- other: visible defect not covered above.
Be strict: between pass and warn pick warn; between warn and fail pick fail if a customer would object."""


def build_batches():
    """Write per-PDF batch files + manifest from review_queue.json. Returns manifest."""
    queue = json.loads((OUT / "review_queue.json").read_text())
    from collections import defaultdict
    grouped = defaultdict(list)
    for e in queue:
        grouped[e["pdf"]].append(e)

    manifest = []
    for pdf, edits in grouped.items():
        slug = re.sub(r"[^A-Za-z0-9]+", "_", pdf)[:30].strip("_")
        items = [{
            "edit_index": e["edit_index"],
            "page": e["page"],
            "target": e["target"],
            "replacement": e["replacement"],
            "crop_before": str((OUT / e["crop_before"]).resolve()),
            "crop_after": str((OUT / e["crop_after"]).resolve()),
        } for e in edits]
        bf = OUT / f"_grade_batch_{slug}.json"
        bf.write_text(json.dumps({"pdf": pdf, "edits": items}, indent=2))
        manifest.append({"pdf": pdf, "slug": slug, "batch_file": str(bf), "n": len(items)})
    (OUT / "_grade_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _api_available():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def grade_via_api(manifest):
    """Grade every edit by sending crop pairs to Claude with structured output."""
    import base64
    import anthropic

    client = anthropic.Anthropic()
    model = os.environ.get("MARCEDIT_GRADER_MODEL", "claude-opus-4-8")
    tool = {
        "name": "record_grade",
        "description": "Record the visual grade for one edit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grade": {"type": "string", "enum": ["pass", "warn", "fail"]},
                "defect": {"type": "string", "enum": DEFECTS},
                "reason": {"type": "string", "description": "<= 12 words"},
            },
            "required": ["grade", "defect", "reason"],
        },
    }
    review = {}
    for m in manifest:
        data = json.loads(Path(m["batch_file"]).read_text())
        for e in data["edits"]:
            blocks = [{"type": "text",
                       "text": f"target: {e['target']!r}\nreplacement: {e['replacement']!r}\nBEFORE then AFTER:"}]
            for p in (e["crop_before"], e["crop_after"]):
                blocks.append({"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": base64.b64encode(Path(p).read_bytes()).decode()}})
            msg = client.messages.create(
                model=model, max_tokens=300, system=RUBRIC,
                tools=[tool], tool_choice={"type": "tool", "name": "record_grade"},
                messages=[{"role": "user", "content": blocks}])
            g = next((b.input for b in msg.content if b.type == "tool_use"), None) or {}
            key = f"{data['pdf']}::{e['edit_index']}"
            review[key] = {"grade": g.get("grade", "warn"), "defect": g.get("defect", "other"),
                           "notes": f"[{g.get('defect','other')}] {g.get('reason','')}",
                           "target": e["target"], "replacement": e["replacement"]}
    (OUT / "review_results.json").write_text(json.dumps(review, indent=2, ensure_ascii=False))
    return review


def main():
    if not (OUT / "review_queue.json").exists():
        print("ERROR: review_queue.json not found — run visual_edit_harness.py first")
        sys.exit(1)
    manifest = build_batches()
    n = sum(m["n"] for m in manifest)
    print(f"Built {len(manifest)} batches covering {n} edits → {OUT}/_grade_batch_*.json")

    if "--emit-only" not in sys.argv and _api_available():
        print("ANTHROPIC_API_KEY present — grading via Claude API…")
        review = grade_via_api(manifest)
        from collections import Counter
        c = Counter(v["grade"] for v in review.values())
        print(f"  graded {len(review)}: pass {c['pass']} / warn {c['warn']} / fail {c['fail']}")
        return 0

    # Agent backend: hand off to the orchestrating session.
    print("\nNo API grader available — emit-only. Grade each batch with a vision agent")
    print("(rubric in grade_edits.RUBRIC), then write review_results.json keyed '<pdf>::<index>'")
    print("with {grade, defect, notes}. Then run: ./.venv311/bin/python tests/grade_gallery.py")
    return 2


if __name__ == "__main__":
    sys.exit(main())
