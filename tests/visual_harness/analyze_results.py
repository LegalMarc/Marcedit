import json
from collections import Counter

output_path = "tests/visual_harness/output/results.json"

try:
    with open(output_path, 'r') as f:
        data = json.load(f)

    results = data.get("results", [])
    
    total = len(results)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    print(f"Total: {total}")
    print(f"PASS: {pass_count}")
    print(f"WARN: {warn_count}")
    print(f"FAIL: {fail_count}")

    # Analyze failure reasons
    reasons = Counter()
    for r in results:
        if r["status"] in ["FAIL", "WARN"]:
            # Simplify reason to base cause
            reason = r["verdict_reason"]
            if "Pixel diff" in reason:
                reason = "Pixel diff"
            elif "Font changed" in reason:
                reason = "Font changed"
            elif "SSIM" in reason:
                reason = "SSIM mismatch"
            reasons[reason] += 1

    print("\n--- Top Failure Reasons ---")
    for reason, count in reasons.most_common(10):
        print(f"{reason}: {count}")

    # Analyze Font mismatches
    font_issues = Counter()
    for r in results:
        if r["status"] in ["FAIL", "WARN"] and "Font changed" in r["verdict_reason"]:
            key = f"{r.get('original_font', '?')} -> {r.get('result_font', '?')}"
            font_issues[key] += 1

    print("\n--- Top Font Substitutions (Org -> Res) ---")
    for pair, count in font_issues.most_common(10):
        print(f"{pair}: {count}")

    # Analyze by File
    file_issues = Counter()
    for r in results:
         if r["status"] == "FAIL":
             file_issues[r["file"]] += 1
    
    print("\n--- Failures by File ---")
    for file, count in file_issues.most_common(5):
        print(f"{file}: {count}")

except Exception as e:
    print(f"Error analyzing results: {e}")
