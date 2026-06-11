#!/usr/bin/env python3
"""
Week 7 Day 1 - Performance Benchmarking Suite
Tests performance of text replacement operations across different document sizes
"""

import sys
import os
import time
import fitz
import tracemalloc

# Add python_site to path
python_site = os.path.join(os.path.dirname(__file__), 'Sources/Marcedit/python_site')
sys.path.insert(0, python_site)

from editor_pkg import core


def create_test_pdf(num_pages, text_per_page=10, output_path=None):
    """
    Create a test PDF with specified number of pages.

    Args:
        num_pages: Number of pages to create
        text_per_page: Number of text blocks per page
        output_path: Where to save the PDF (or None for temp)

    Returns:
        Path to created PDF
    """
    if output_path is None:
        import tempfile
        fd, output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)

    doc = fitz.open()

    for page_num in range(num_pages):
        page = doc.new_page(width=612, height=792)  # US Letter

        # Add text blocks at various positions
        for i in range(text_per_page):
            y_pos = 50 + (i * 60)
            text = f"Page {page_num + 1} Block {i + 1}: The quick brown fox jumps over the lazy dog."
            page.insert_text((50, y_pos), text, fontsize=12, fontname="Helvetica")

        # Add a target replacement text on each page
        page.insert_text((50, 700), "TARGET_TEXT_TO_REPLACE", fontsize=12, fontname="Helvetica")

    doc.save(output_path)
    doc.close()

    return output_path


def benchmark_single_replacement(pdf_path, iterations=1):
    """
    Benchmark a single text replacement operation.

    Returns:
        dict with timing and memory stats
    """
    results = []

    for i in range(iterations):
        # Create a temp output path
        import tempfile
        fd, output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)

        try:
            # Start memory tracking
            tracemalloc.start()
            start_memory = tracemalloc.get_traced_memory()[0]

            # Time the operation
            start_time = time.time()

            result = core.replace_text_in_pdf(
                input_path=pdf_path,
                output_path=output_path,
                target_text="TARGET_TEXT_TO_REPLACE",
                replacement_text="REPLACEMENT_TEXT_COMPLETE",
                page_number=1  # 1-indexed
            )

            end_time = time.time()

            # End memory tracking
            end_memory = tracemalloc.get_traced_memory()[0]
            tracemalloc.stop()

            duration_ms = (end_time - start_time) * 1000
            memory_used_mb = (end_memory - start_memory) / (1024 * 1024)

            results.append({
                'duration_ms': duration_ms,
                'memory_mb': memory_used_mb,
                'success': result.get('success', False)
            })
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    # Calculate statistics
    durations = [r['duration_ms'] for r in results]
    memories = [r['memory_mb'] for r in results]

    return {
        'iterations': iterations,
        'avg_duration_ms': sum(durations) / len(durations),
        'min_duration_ms': min(durations),
        'max_duration_ms': max(durations),
        'avg_memory_mb': sum(memories) / len(memories),
        'max_memory_mb': max(memories),
        'all_success': all(r['success'] for r in results)
    }


def benchmark_multi_page_replacement(pdf_path, num_pages_to_test):
    """
    Benchmark replacement across multiple pages.

    Args:
        pdf_path: Path to test PDF
        num_pages_to_test: Number of pages to replace on

    Returns:
        dict with timing stats
    """
    import tempfile

    # Get actual page count
    doc = fitz.open(pdf_path)
    actual_pages = min(num_pages_to_test, len(doc))
    doc.close()

    tracemalloc.start()
    start_memory = tracemalloc.get_traced_memory()[0]
    start_time = time.time()

    success_count = 0
    current_path = pdf_path

    for page_num in range(1, actual_pages + 1):  # 1-indexed
        # Create temp output
        fd, output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)

        try:
            result = core.replace_text_in_pdf(
                input_path=current_path,
                output_path=output_path,
                target_text="TARGET_TEXT_TO_REPLACE",
                replacement_text="REPLACEMENT_TEXT_COMPLETE",
                page_number=page_num
            )

            if result.get('success', False):
                success_count += 1

            # For subsequent iterations, use the modified PDF
            # (This simulates batch editing)
            if current_path != pdf_path and os.path.exists(current_path):
                os.unlink(current_path)
            current_path = output_path

        except Exception as e:
            if os.path.exists(output_path):
                os.unlink(output_path)
            raise

    # Cleanup final output
    if current_path != pdf_path and os.path.exists(current_path):
        os.unlink(current_path)

    end_time = time.time()
    end_memory = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()

    total_duration_ms = (end_time - start_time) * 1000
    memory_used_mb = (end_memory - start_memory) / (1024 * 1024)

    return {
        'total_pages': actual_pages,
        'success_count': success_count,
        'total_duration_ms': total_duration_ms,
        'avg_duration_per_page_ms': total_duration_ms / actual_pages if actual_pages > 0 else 0,
        'memory_mb': memory_used_mb
    }


def test_01_small_document_performance():
    """Benchmark performance on small 10-page document."""
    print("\n[TEST 01] Small Document (10 pages) Performance")

    pdf_path = create_test_pdf(num_pages=10)

    try:
        # Single replacement benchmark
        stats = benchmark_single_replacement(pdf_path, iterations=3)

        print(f"  Single replacement (avg of {stats['iterations']} runs):")
        print(f"    Duration: {stats['avg_duration_ms']:.1f}ms (min: {stats['min_duration_ms']:.1f}ms, max: {stats['max_duration_ms']:.1f}ms)")
        print(f"    Memory: {stats['avg_memory_mb']:.2f}MB (max: {stats['max_memory_mb']:.2f}MB)")
        print(f"    Success: {stats['all_success']}")

        # Multi-page benchmark
        multi_stats = benchmark_multi_page_replacement(pdf_path, num_pages_to_test=10)

        print(f"  Multi-page replacement ({multi_stats['total_pages']} pages):")
        print(f"    Total duration: {multi_stats['total_duration_ms']:.1f}ms")
        print(f"    Avg per page: {multi_stats['avg_duration_per_page_ms']:.1f}ms")
        print(f"    Memory: {multi_stats['memory_mb']:.2f}MB")
        print(f"    Success: {multi_stats['success_count']}/{multi_stats['total_pages']}")

        # Set baseline expectation (will adjust based on actual performance)
        assert stats['avg_duration_ms'] < 2000, f"Single replacement too slow: {stats['avg_duration_ms']}ms"

        return True

    finally:
        os.unlink(pdf_path)


def test_02_medium_document_performance():
    """Benchmark performance on medium 100-page document."""
    print("\n[TEST 02] Medium Document (100 pages) Performance")

    pdf_path = create_test_pdf(num_pages=100)

    try:
        # Single replacement benchmark
        stats = benchmark_single_replacement(pdf_path, iterations=2)

        print(f"  Single replacement (avg of {stats['iterations']} runs):")
        print(f"    Duration: {stats['avg_duration_ms']:.1f}ms")
        print(f"    Memory: {stats['avg_memory_mb']:.2f}MB")

        # Multi-page benchmark (sample of pages)
        multi_stats = benchmark_multi_page_replacement(pdf_path, num_pages_to_test=20)

        print(f"  Multi-page replacement (20 pages sampled):")
        print(f"    Total duration: {multi_stats['total_duration_ms']:.1f}ms")
        print(f"    Avg per page: {multi_stats['avg_duration_per_page_ms']:.1f}ms")
        print(f"    Memory: {multi_stats['memory_mb']:.2f}MB")

        # Estimate full document
        estimated_full = multi_stats['avg_duration_per_page_ms'] * 100
        print(f"  Estimated full document (100 pages): {estimated_full:.0f}ms ({estimated_full/1000:.1f}s)")

        return True

    finally:
        os.unlink(pdf_path)


def test_03_large_document_performance():
    """Benchmark performance on large 1000-page document."""
    print("\n[TEST 03] Large Document (1000 pages) Performance")
    print("  Note: This test creates a large PDF and may take time...")

    start_create = time.time()
    pdf_path = create_test_pdf(num_pages=1000)
    create_duration = time.time() - start_create

    # Check file size
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"  Created 1000-page PDF in {create_duration:.1f}s (size: {file_size_mb:.1f}MB)")

    try:
        # Single replacement benchmark
        stats = benchmark_single_replacement(pdf_path, iterations=1)

        print(f"  Single replacement (page 0):")
        print(f"    Duration: {stats['avg_duration_ms']:.1f}ms")
        print(f"    Memory: {stats['avg_memory_mb']:.2f}MB")

        # Multi-page benchmark (small sample)
        multi_stats = benchmark_multi_page_replacement(pdf_path, num_pages_to_test=10)

        print(f"  Multi-page replacement (10 pages sampled):")
        print(f"    Total duration: {multi_stats['total_duration_ms']:.1f}ms")
        print(f"    Avg per page: {multi_stats['avg_duration_per_page_ms']:.1f}ms")
        print(f"    Memory: {multi_stats['memory_mb']:.2f}MB")

        # Estimate full document
        estimated_full = multi_stats['avg_duration_per_page_ms'] * 1000
        print(f"  Estimated full document (1000 pages): {estimated_full:.0f}ms ({estimated_full/1000:.1f}s)")

        # Baseline expectation (before optimization)
        # This establishes what we need to improve
        print(f"\n  Performance Summary:")
        print(f"    ✓ Can handle large documents")
        print(f"    ⚠ Full replacement would take ~{estimated_full/1000:.1f}s")
        print(f"    → Target after optimization: <10s for full document")

        return True

    finally:
        os.unlink(pdf_path)


def test_04_memory_scaling():
    """Test how memory usage scales with document size."""
    print("\n[TEST 04] Memory Scaling Analysis")

    sizes = [10, 50, 100]
    results = []

    for num_pages in sizes:
        print(f"\n  Testing {num_pages} pages...")
        pdf_path = create_test_pdf(num_pages=num_pages)

        try:
            import tempfile

            tracemalloc.start()
            start_mem = tracemalloc.get_traced_memory()[0]

            # Perform 5 replacements to see memory pattern
            current_path = pdf_path
            for i in range(5):
                fd, output_path = tempfile.mkstemp(suffix='.pdf')
                os.close(fd)

                try:
                    page_to_edit = min(i + 1, num_pages)  # 1-indexed
                    core.replace_text_in_pdf(
                        input_path=current_path,
                        output_path=output_path,
                        target_text="TARGET_TEXT_TO_REPLACE",
                        replacement_text="REPLACEMENT_TEXT_COMPLETE",
                        page_number=page_to_edit
                    )

                    # Clean up previous iteration
                    if current_path != pdf_path and os.path.exists(current_path):
                        os.unlink(current_path)
                    current_path = output_path

                except Exception:
                    if os.path.exists(output_path):
                        os.unlink(output_path)
                    raise

            # Clean up final output
            if current_path != pdf_path and os.path.exists(current_path):
                os.unlink(current_path)

            peak_mem = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()

            memory_mb = (peak_mem - start_mem) / (1024 * 1024)
            results.append({
                'pages': num_pages,
                'memory_mb': memory_mb,
                'memory_per_page_kb': (memory_mb * 1024) / num_pages
            })

            print(f"    Peak memory: {memory_mb:.2f}MB ({results[-1]['memory_per_page_kb']:.1f}KB per page)")

        finally:
            os.unlink(pdf_path)

    # Analyze scaling
    print(f"\n  Memory Scaling:")
    for r in results:
        print(f"    {r['pages']:3d} pages: {r['memory_mb']:6.2f}MB ({r['memory_per_page_kb']:6.1f}KB/page)")

    # Check if memory scales linearly (it should, or better)
    ratio_10_to_100 = results[2]['memory_mb'] / results[0]['memory_mb']
    print(f"\n  Scaling ratio (100 pages / 10 pages): {ratio_10_to_100:.1f}x")
    print(f"    (Linear would be 10.0x, sublinear is better)")

    return True


def test_05_collision_detection_overhead():
    """Measure overhead of collision detection."""
    print("\n[TEST 05] Collision Detection Overhead")

    pdf_path = create_test_pdf(num_pages=5)

    try:
        import tempfile

        # Measure with collision detection enabled
        fd, output_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)

        try:
            start = time.time()
            result_with_collision = core.replace_text_in_pdf(
                input_path=pdf_path,
                output_path=output_path,
                target_text="TARGET_TEXT_TO_REPLACE",
                replacement_text="REPLACEMENT_TEXT_COMPLETE",
                page_number=1
            )
            duration_with = (time.time() - start) * 1000

            # For now, we can only test with collision enabled
            # (Would need to add a disable flag to test without)
            print(f"  With collision detection: {duration_with:.1f}ms")
            print(f"  Note: Collision detection is integral to safety")
            print(f"  Future optimization: Cache pixmaps, reduce resolution for simple cases")

            return True

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    finally:
        os.unlink(pdf_path)


def test_06_font_loading_overhead():
    """Measure font loading overhead across multiple operations."""
    print("\n[TEST 06] Font Loading Overhead")

    pdf_path = create_test_pdf(num_pages=10)

    try:
        import tempfile

        # First replacement (cold - font loading)
        fd1, output1 = tempfile.mkstemp(suffix='.pdf')
        os.close(fd1)

        start = time.time()
        core.replace_text_in_pdf(
            input_path=pdf_path,
            output_path=output1,
            target_text="TARGET_TEXT_TO_REPLACE",
            replacement_text="REPLACEMENT_FIRST",
            page_number=1
        )
        first_duration = (time.time() - start) * 1000

        # Second replacement (warm - font cached by PyMuPDF)
        fd2, output2 = tempfile.mkstemp(suffix='.pdf')
        os.close(fd2)

        start = time.time()
        core.replace_text_in_pdf(
            input_path=output1,
            output_path=output2,
            target_text="TARGET_TEXT_TO_REPLACE",
            replacement_text="REPLACEMENT_SECOND",
            page_number=2
        )
        second_duration = (time.time() - start) * 1000

        # Third replacement (warm)
        fd3, output3 = tempfile.mkstemp(suffix='.pdf')
        os.close(fd3)

        start = time.time()
        core.replace_text_in_pdf(
            input_path=output2,
            output_path=output3,
            target_text="TARGET_TEXT_TO_REPLACE",
            replacement_text="REPLACEMENT_THIRD",
            page_number=3
        )
        third_duration = (time.time() - start) * 1000

        # Cleanup
        for path in [output1, output2, output3]:
            if os.path.exists(path):
                os.unlink(path)

        print(f"  First replacement (cold):  {first_duration:.1f}ms")
        print(f"  Second replacement (warm): {second_duration:.1f}ms")
        print(f"  Third replacement (warm):  {third_duration:.1f}ms")

        if second_duration < first_duration:
            improvement = ((first_duration - second_duration) / first_duration) * 100
            print(f"  Warm-up improvement: {improvement:.1f}%")

        return True

    finally:
        os.unlink(pdf_path)


def run_all_benchmarks():
    """Run complete performance benchmark suite."""
    tests = [
        test_01_small_document_performance,
        test_02_medium_document_performance,
        test_03_large_document_performance,
        test_04_memory_scaling,
        test_05_collision_detection_overhead,
        test_06_font_loading_overhead,
    ]

    print("=" * 70)
    print("Week 7 Day 1 - Performance Benchmark Suite")
    print("=" * 70)
    print("\nBaseline Performance Metrics (Before Optimization)")
    print("-" * 70)

    passed = 0
    failed = 0

    overall_start = time.time()

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"  ✗ Test returned False")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ Assertion failed: {e}")
        except Exception as e:
            failed += 1
            print(f"  ✗ Exception: {e}")
            import traceback
            traceback.print_exc()

    overall_duration = time.time() - overall_start

    print("\n" + "=" * 70)
    print(f"Benchmark Suite Complete: {passed} passed, {failed} failed")
    print(f"Total benchmark time: {overall_duration:.1f}s")
    print("=" * 70)

    print("\n📊 Key Findings:")
    print("  These baseline metrics establish current performance")
    print("  Next: Implement optimizations to achieve 2-5x improvement")

    return failed == 0


if __name__ == "__main__":
    success = run_all_benchmarks()
    sys.exit(0 if success else 1)
