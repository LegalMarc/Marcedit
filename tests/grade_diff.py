"""
grade_diff.py — incremental re-grading for the visual loop.

The harness is deterministic (seed 42), so after a code change most edits render
byte-for-byte identical to the previous run. This compares the current crops to a
saved snapshot and:
  * carries forward the previous grade for every UNCHANGED edit, and
  * lists the CHANGED edits (the only ones that need a fresh visual grade).

That turns each loop iteration from "re-grade all 86" into "re-grade the handful
that actually changed".

Usage:
    # 1. snapshot the previous run BEFORE re-driving:
    cp -r tests/visual_edit_harness_report tests/visual_edit_harness_report_prev
    # 2. re-run the harness (overwrites crops in place)
    # 3. diff:
    ./.venv311/bin/python tests/grade_diff.py
        -> writes review_results.json with carried-forward grades for unchanged edits
        -> prints the changed edits + a _regrade_manifest.json for the grader
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CUR = ROOT / "visual_edit_harness_report"
PREV = ROOT / "visual_edit_harness_report_prev"


def _digest(p: Path):
    try:
        return hashlib.md5(p.read_bytes()).hexdigest()
    except OSError:
        return None


def main():
    if not PREV.exists():
        print(f"No snapshot at {PREV} — nothing to diff against. Grade all edits fresh.")
        return 1
    queue = json.loads((CUR / "review_queue.json").read_text())
    prev_grades = {}
    pg_path = PREV / "review_results.json"
    if pg_path.exists():
        prev_grades = json.loads(pg_path.read_text())

    carried, changed = {}, []
    for e in queue:
        key = f"{e['pdf']}::{e['edit_index']}"
        cur_after = CUR / e["crop_after"]
        prev_after = PREV / e["crop_after"]
        same = (_digest(cur_after) is not None and _digest(cur_after) == _digest(prev_after))
        if same and key in prev_grades:
            carried[key] = prev_grades[key]
        else:
            changed.append(e)

    # Seed review_results.json with the carried-forward (unchanged) grades.
    (CUR / "review_results.json").write_text(json.dumps(carried, indent=2, ensure_ascii=False))

    # Group changed edits by PDF for the grader to fan out over.
    from collections import defaultdict
    by_pdf = defaultdict(list)
    for e in changed:
        by_pdf[e["pdf"]].append(e["edit_index"])
    manifest = [{"pdf": k, "edit_indices": sorted(v)} for k, v in by_pdf.items()]
    (CUR / "_regrade_manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"unchanged (grade carried forward): {len(carried)}")
    print(f"CHANGED (need re-grade): {len(changed)}")
    for e in changed:
        print(f"  {e['pdf'][:40]:40s} e{e['edit_index']:<2} "
              f"{e['target'][:20]!r:22} -> {e['replacement'][:20]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
