#!/usr/bin/env python3
"""
Diagnostic tests to measure where latency is coming from.
Separates AppleScript overhead from actual app responsiveness.
"""

import subprocess
import time
import json
from pathlib import Path
from typing import Dict, Any

from . import interactions
from . import observer


def measure_applescript_overhead(iterations: int = 10) -> Dict[str, Any]:
    """
    Measure raw AppleScript execution time to establish baseline.
    """
    results = {
        'simple_query': [],
        'window_query': [],
        'element_query': [],
        'click_action': [],
    }

    # 1. Simple AppleScript (minimal)
    for _ in range(iterations):
        start = time.perf_counter()
        interactions.run_applescript('return "hello"')
        results['simple_query'].append((time.perf_counter() - start) * 1000)

    # 2. Window position query
    for _ in range(iterations):
        start = time.perf_counter()
        interactions.get_window_position('Marcedit')
        results['window_query'].append((time.perf_counter() - start) * 1000)

    # 3. UI element query
    for _ in range(iterations):
        start = time.perf_counter()
        interactions.element_exists('SaveButton', 'Marcedit')
        results['element_query'].append((time.perf_counter() - start) * 1000)

    # 4. Click action (includes activate + click)
    pos = interactions.get_window_position('Marcedit')
    if pos:
        for _ in range(iterations):
            start = time.perf_counter()
            interactions.click_at_coordinates(pos[0] + 200, pos[1] + 200, 'Marcedit')
            results['click_action'].append((time.perf_counter() - start) * 1000)

    # Calculate statistics
    summary = {}
    for key, times in results.items():
        if times:
            summary[key] = {
                'avg_ms': sum(times) / len(times),
                'min_ms': min(times),
                'max_ms': max(times),
                'samples': len(times),
            }

    return summary


def measure_screenshot_overhead(iterations: int = 5) -> Dict[str, Any]:
    """
    Measure screenshot capture time.
    """
    results = {
        'full_screen': [],
        'window_capture': [],
    }

    for _ in range(iterations):
        start = time.perf_counter()
        path = observer.capture_screenshot()
        results['full_screen'].append((time.perf_counter() - start) * 1000)
        Path(path).unlink()  # Clean up

    for _ in range(iterations):
        start = time.perf_counter()
        path = observer.capture_window('Marcedit')
        results['window_capture'].append((time.perf_counter() - start) * 1000)
        Path(path).unlink()  # Clean up

    summary = {}
    for key, times in results.items():
        if times:
            summary[key] = {
                'avg_ms': sum(times) / len(times),
                'min_ms': min(times),
                'max_ms': max(times),
            }

    return summary


def measure_ui_change_detection(app_name: str = 'Marcedit') -> Dict[str, Any]:
    """
    Measure how quickly we can detect a UI change after an action.
    Uses screenshot hash comparison.
    """
    results = []

    pos = interactions.get_window_position(app_name)
    if not pos:
        return {'error': 'Could not get window position'}

    # Try clicking in different areas and measuring hash change time
    click_points = [
        (pos[0] + 100, pos[1] + 100),
        (pos[0] + 200, pos[1] + 150),
        (pos[0] + 300, pos[1] + 200),
    ]

    for x, y in click_points:
        # Get initial hash
        initial_hash = observer.capture_window_hash(app_name)

        # Click and measure time to hash change
        start = time.perf_counter()
        interactions.click_at_coordinates(x, y, app_name)

        # Poll for change (up to 2 seconds)
        changed = False
        change_time = None
        while time.perf_counter() - start < 2.0:
            current_hash = observer.capture_window_hash(app_name)
            if current_hash != initial_hash:
                change_time = (time.perf_counter() - start) * 1000
                changed = True
                break
            time.sleep(0.016)  # ~60fps polling

        results.append({
            'click_pos': (x, y),
            'changed': changed,
            'change_time_ms': change_time,
            'initial_hash': initial_hash[:8],
        })

        time.sleep(0.5)  # Wait between tests

    return {
        'tests': results,
        'avg_detection_ms': sum(r['change_time_ms'] for r in results if r['change_time_ms']) / max(1, sum(1 for r in results if r['change_time_ms'])) if any(r['change_time_ms'] for r in results) else None
    }


def run_latency_diagnostic() -> Dict[str, Any]:
    """
    Run full latency diagnostic suite.
    """
    print("Running latency diagnostics...")

    results = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    }

    print("  [1/3] Measuring AppleScript overhead...")
    results['applescript_overhead'] = measure_applescript_overhead()

    print("  [2/3] Measuring screenshot overhead...")
    results['screenshot_overhead'] = measure_screenshot_overhead()

    print("  [3/3] Measuring UI change detection...")
    results['ui_change_detection'] = measure_ui_change_detection()

    # Analysis
    print("\n=== Latency Breakdown ===")

    as_overhead = results['applescript_overhead']
    print(f"\nAppleScript overhead:")
    for key, stats in as_overhead.items():
        print(f"  {key}: avg={stats['avg_ms']:.1f}ms, min={stats['min_ms']:.1f}ms, max={stats['max_ms']:.1f}ms")

    ss_overhead = results['screenshot_overhead']
    print(f"\nScreenshot overhead:")
    for key, stats in ss_overhead.items():
        print(f"  {key}: avg={stats['avg_ms']:.1f}ms")

    ui_detect = results['ui_change_detection']
    if 'avg_detection_ms' in ui_detect and ui_detect['avg_detection_ms']:
        print(f"\nUI change detection: avg={ui_detect['avg_detection_ms']:.1f}ms")

    # Calculate where the 450ms is going
    baseline_overhead = as_overhead.get('click_action', {}).get('avg_ms', 0)
    print(f"\n=== Summary ===")
    print(f"Raw click action time: {baseline_overhead:.1f}ms")
    print(f"This represents AppleScript/System Events overhead")

    if baseline_overhead > 300:
        print(f"\nDIAGNOSIS: Most latency ({baseline_overhead:.0f}ms) is AppleScript overhead.")
        print("This is normal for macOS accessibility APIs. The app itself may be responsive.")
        results['diagnosis'] = 'applescript_overhead'
    else:
        print(f"\nDIAGNOSIS: AppleScript overhead is acceptable ({baseline_overhead:.0f}ms).")
        print("Additional latency may indicate actual app responsiveness issues.")
        results['diagnosis'] = 'potential_app_issue'

    return results


if __name__ == '__main__':
    results = run_latency_diagnostic()

    # Save results
    output_path = Path('/tmp/gui_latency_diagnostic.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")
