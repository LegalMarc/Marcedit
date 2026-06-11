#!/usr/bin/env python3
"""
Marcedit Visual Verification Battery - Main Entry Point

Usage:
    python -m tests.visual_harness.run_tests [--generate] [--run] [--report] [--all]
    python -m tests.visual_harness.run_tests --all --llm-eval --fix-report

Options:
    --generate    Generate test cases from sample PDFs
    --run         Execute test cases
    --report      Build PDF report from results
    --all         Do all of the above (default)
    --llm-eval    Run LLM evaluation on results (requires ANTHROPIC_API_KEY)
    --fix-report  Generate fix suggestions from LLM evaluations
    --tests       Comma-separated list of test IDs to run (e.g., TC-001,TC-015)
    --skip-passed Skip tests with PASS status for LLM evaluation (default: True)
"""

import os
import sys
import argparse
import json

# Ensure we can import local modules
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HARNESS_DIR))
sys.path.insert(0, PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(
        description="Marcedit Visual Verification Battery"
    )
    parser.add_argument("--generate", action="store_true",
                        help="Generate test cases from sample PDFs")
    parser.add_argument("--run", action="store_true",
                        help="Execute test cases")
    parser.add_argument("--report", action="store_true",
                        help="Build PDF report from results")
    parser.add_argument("--all", action="store_true",
                        help="Do all steps (default if no flags given)")
    parser.add_argument("--samples", type=str, default=None,
                        help="Comma-separated list of sample directories")
    parser.add_argument("--llm-eval", action="store_true",
                        help="Run LLM evaluation on results (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--fix-report", action="store_true",
                        help="Generate fix suggestions from LLM evaluations")
    parser.add_argument("--tests", type=str, default=None,
                        help="Comma-separated list of test IDs to run (e.g., TC-001,TC-015)")
    parser.add_argument("--skip-passed", action="store_true", default=True,
                        help="Skip tests with PASS status for LLM evaluation (default: True)")
    parser.add_argument("--no-skip-passed", action="store_false", dest="skip_passed",
                        help="Include PASS tests in LLM evaluation")

    args = parser.parse_args()

    # Default to --all if no specific step selected (excluding LLM options)
    if not any([args.generate, args.run, args.report, args.llm_eval, args.fix_report]):
        args.all = True
    
    # Determine sample directories
    if args.samples:
        sample_dirs = [s.strip() for s in args.samples.split(",")]
    else:
        sample_dirs = [
            os.path.join(HARNESS_DIR, "samples"),
            os.path.join(PROJECT_ROOT, "ignored-resources", "sample-files")
        ]
    
    output_dir = os.path.join(HARNESS_DIR, "output")
    manifest_path = os.path.join(output_dir, "test_manifest.json")
    results_path = os.path.join(output_dir, "results.json")
    report_path = os.path.join(output_dir, "Visual_Regression_Report.pdf")
    llm_eval_path = os.path.join(output_dir, "llm_evaluations.json")
    fix_report_path = os.path.join(output_dir, "fix_suggestions.md")
    images_dir = os.path.join(output_dir, "images")

    os.makedirs(output_dir, exist_ok=True)

    # Parse test filter if provided
    test_filter = None
    if args.tests:
        test_filter = set(t.strip() for t in args.tests.split(","))
    
    # Step 1: Generate test cases
    if args.generate or args.all:
        print("\n" + "=" * 60)
        print("STEP 1: Generating Test Cases")
        print("=" * 60)
        
        from tests.visual_harness.test_generator import generate_tests
        tests = generate_tests(sample_dirs, manifest_path)
        print(f"Generated {len(tests)} test cases")
    
    # Step 2: Run tests
    if args.run or args.all:
        print("\n" + "=" * 60)
        print("STEP 2: Running Tests")
        print("=" * 60)
        
        if not os.path.exists(manifest_path):
            print(f"Error: No manifest found at {manifest_path}")
            print("Run with --generate first")
            return 1
        
        from tests.visual_harness.test_runner import run_tests
        results = run_tests(manifest_path, output_dir)
        
        # Quick summary
        summary = {
            "pass": sum(1 for r in results if r.status == "PASS"),
            "warn": sum(1 for r in results if r.status == "WARN"),
            "fail": sum(1 for r in results if r.status == "FAIL"),
            "error": sum(1 for r in results if r.status == "ERROR"),
        }
        print(f"\nResults: {summary}")
    
    # Step 3: Build report
    if args.report or args.all:
        print("\n" + "=" * 60)
        print("STEP 3: Building PDF Report")
        print("=" * 60)

        if not os.path.exists(results_path):
            print(f"Error: No results found at {results_path}")
            print("Run with --run first")
            return 1

        from tests.visual_harness.report_builder import build_report
        build_report(results_path, report_path)
        print(f"\nReport ready: {report_path}")

    # Step 4: LLM Evaluation (optional)
    llm_evaluations = None
    if args.llm_eval:
        print("\n" + "=" * 60)
        print("STEP 4: Running LLM Evaluation")
        print("=" * 60)

        if not os.path.exists(results_path):
            print(f"Error: No results found at {results_path}")
            print("Run with --run first")
            return 1

        # Check for API key
        from tests.visual_harness import config
        is_valid, error = config.validate_config()
        if not is_valid:
            print(f"Error: {error}")
            print("Set ANTHROPIC_API_KEY environment variable and try again")
            return 1

        # Load results
        with open(results_path, 'r') as f:
            results_data = json.load(f)
        results = results_data.get("results", [])

        # Filter by test IDs if specified
        if test_filter:
            results = [r for r in results if r.get("test_id") in test_filter]
            print(f"Filtered to {len(results)} tests: {', '.join(test_filter)}")

        if not results:
            print("No tests to evaluate")
        else:
            from tests.visual_harness.llm_evaluator import LLMEvaluator, save_evaluations

            def progress(current, total, tc_id):
                print(f"\r[{current}/{total}] Evaluating {tc_id}...", end="", flush=True)

            try:
                evaluator = LLMEvaluator()
                llm_evaluations = evaluator.evaluate_batch(
                    results,
                    images_dir=images_dir,
                    progress_callback=progress,
                    skip_passed=args.skip_passed
                )
                print()  # Newline after progress

                save_evaluations(llm_evaluations, llm_eval_path)

                # Quick summary
                verdicts = {}
                for ev in llm_evaluations:
                    v = ev.verdict
                    verdicts[v] = verdicts.get(v, 0) + 1
                print(f"LLM Verdicts: {verdicts}")

            except ImportError as e:
                print(f"Error: {e}")
                print("Install anthropic package: pip install anthropic")
                return 1
            except ValueError as e:
                print(f"Configuration error: {e}")
                return 1

    # Step 5: Fix Report (optional)
    if args.fix_report:
        print("\n" + "=" * 60)
        print("STEP 5: Generating Fix Suggestions")
        print("=" * 60)

        # Use evaluations from this run or load from file
        if llm_evaluations is None:
            if not os.path.exists(llm_eval_path):
                print(f"Error: No LLM evaluations found at {llm_eval_path}")
                print("Run with --llm-eval first")
                return 1

            from tests.visual_harness.fix_suggester import generate_fix_report
            generate_fix_report(llm_eval_path, fix_report_path)
        else:
            from tests.visual_harness.fix_suggester import generate_fix_report_from_evaluations
            generate_fix_report_from_evaluations(llm_evaluations, fix_report_path)

        print(f"\nFix report ready: {fix_report_path}")

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"\nOutput files:")
    if os.path.exists(report_path):
        print(f"  - PDF Report: {report_path}")
    if os.path.exists(llm_eval_path):
        print(f"  - LLM Evaluations: {llm_eval_path}")
    if os.path.exists(fix_report_path):
        print(f"  - Fix Suggestions: {fix_report_path}")

    print(f"\nNext steps:")
    if os.path.exists(fix_report_path):
        print(f"1. Review fix suggestions: cat {fix_report_path}")
    if os.path.exists(report_path):
        print(f"2. Open the visual report: open {report_path}")
    print(f"3. Make fixes and re-run: python -m tests.visual_harness.run_tests --run --llm-eval")

    return 0


if __name__ == "__main__":
    sys.exit(main())
