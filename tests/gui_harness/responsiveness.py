#!/usr/bin/env python3
"""
UI responsiveness and layout stability testing module.
Detects freezes, lag, jumping elements, and jank.
"""

import subprocess
import time
import json
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from . import observer
from . import interactions


@dataclass
class ResponsivenessResult:
    """Result of a responsiveness measurement."""
    latency_ms: float
    responsive: bool
    timed_out: bool
    rating: str  # 'excellent', 'good', 'acceptable', 'slow', 'frozen'


@dataclass
class LayoutShift:
    """Record of a detected layout shift."""
    element: str
    frame: int
    from_pos: tuple
    to_pos: tuple
    delta_px: float


@dataclass
class StabilityResult:
    """Result of layout stability measurement."""
    shifts: List[LayoutShift]
    stability_score: float  # 0-100
    total_shifts: int
    max_shift_px: float
    verdict: str  # 'stable', 'minor_shifts', 'unstable'


def measure_action_latency(
    action_fn: Callable,
    check_fn: Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.016,
    baseline_overhead: float = 310.0  # AppleScript overhead in ms
) -> ResponsivenessResult:
    """
    Measure time between action and visible response.

    Args:
        action_fn: Function that triggers the UI action.
        check_fn: Function that returns True when UI has responded.
        timeout: Maximum wait time in seconds.
        poll_interval: How often to check for response (default ~60fps).
        baseline_overhead: AppleScript/accessibility API overhead to subtract (ms).

    Returns:
        ResponsivenessResult with latency and responsiveness info.

    Note:
        macOS AppleScript/System Events adds ~300-350ms overhead to any click action.
        This is subtracted from measurements to get actual app responsiveness.
    """
    start = time.perf_counter()

    # Perform the action
    action_fn()

    # Poll for change
    while time.perf_counter() - start < timeout:
        try:
            if check_fn():
                raw_latency = (time.perf_counter() - start) * 1000  # Convert to ms
                # Subtract baseline AppleScript overhead for true app latency
                latency = max(0, raw_latency - baseline_overhead)

                # Determine rating based on app-only latency
                if latency < 50:
                    rating = 'excellent'
                elif latency < 100:
                    rating = 'good'
                elif latency < 200:
                    rating = 'acceptable'
                elif latency < 500:
                    rating = 'slow'
                else:
                    rating = 'very_slow'

                return ResponsivenessResult(
                    latency_ms=raw_latency,  # Report raw for transparency
                    responsive=latency < 200,  # App-only latency threshold
                    timed_out=False,
                    rating=rating
                )
        except Exception:
            pass

        time.sleep(poll_interval)

    return ResponsivenessResult(
        latency_ms=timeout * 1000,
        responsive=False,
        timed_out=True,
        rating='frozen'
    )


def detect_beach_ball(app_name: str = 'Marcedit') -> bool:
    """
    Detect if the spinning wait cursor (beach ball) is showing.
    Indicates the app is unresponsive.
    """
    return interactions.is_app_busy(app_name)


def monitor_responsiveness(
    duration: float = 10.0,
    interval: float = 0.1,
    app_name: str = 'Marcedit'
) -> Dict[str, Any]:
    """
    Monitor app responsiveness over a period of time.
    Detects freezes and beach balls.

    Args:
        duration: How long to monitor in seconds.
        interval: Check interval in seconds.
        app_name: Application to monitor.

    Returns:
        Dict with freeze events and statistics.
    """
    freezes = []
    samples = []
    start = time.time()
    frozen_since = None

    while time.time() - start < duration:
        timestamp = time.time() - start
        is_busy = detect_beach_ball(app_name)

        samples.append({
            'time': timestamp,
            'busy': is_busy
        })

        if is_busy:
            if frozen_since is None:
                frozen_since = timestamp
        else:
            if frozen_since is not None:
                freeze_duration = timestamp - frozen_since
                if freeze_duration > 0.3:  # Only record freezes > 300ms
                    freezes.append({
                        'start': frozen_since,
                        'duration': freeze_duration,
                        'type': 'beach_ball'
                    })
                frozen_since = None

        time.sleep(interval)

    # Check if still frozen at end
    if frozen_since is not None:
        freezes.append({
            'start': frozen_since,
            'duration': time.time() - start - frozen_since,
            'type': 'beach_ball',
            'ongoing': True
        })

    total_frozen_time = sum(f['duration'] for f in freezes)

    return {
        'duration': duration,
        'freezes': freezes,
        'freeze_count': len(freezes),
        'total_frozen_time': total_frozen_time,
        'frozen_percentage': (total_frozen_time / duration) * 100,
        'responsive': len(freezes) == 0
    }


def get_element_positions(app_name: str = 'Marcedit') -> Dict[str, tuple]:
    """
    Get positions of all accessible UI elements.
    """
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            set output to ""
            if (count of windows) > 0 then
                repeat with elem in entire contents of window 1
                    try
                        set elemDesc to description of elem as string
                        set elemPos to position of elem
                        if elemDesc is not "" then
                            set output to output & elemDesc & ":" & (item 1 of elemPos) & "," & (item 2 of elemPos) & linefeed
                        end if
                    end try
                end repeat
            end if
            return output
        end tell
    end tell
    '''
    result = interactions.run_applescript(script)

    positions = {}
    for line in result.strip().split('\n'):
        if ':' in line and ',' in line:
            try:
                name, coords = line.rsplit(':', 1)
                x, y = map(int, coords.split(','))
                positions[name.strip()] = (x, y)
            except (ValueError, IndexError):
                pass

    return positions


def measure_layout_stability(
    action_fn: Callable,
    sample_count: int = 30,
    interval: float = 0.033,  # ~30fps
    app_name: str = 'Marcedit'
) -> StabilityResult:
    """
    Measure layout stability during and after an action.
    Detects unexpected element position changes (layout shifts).

    Args:
        action_fn: Function that triggers the action to test.
        sample_count: Number of position samples to capture.
        interval: Time between samples.
        app_name: Application to monitor.

    Returns:
        StabilityResult with shift details and stability score.
    """
    positions_over_time = []

    # Capture before
    positions_over_time.append(get_element_positions(app_name))

    # Trigger action
    action_fn()

    # Rapid sampling after action
    for _ in range(sample_count):
        positions_over_time.append(get_element_positions(app_name))
        time.sleep(interval)

    # Analyze for unexpected shifts
    shifts = []

    for i in range(1, len(positions_over_time)):
        prev = positions_over_time[i - 1]
        curr = positions_over_time[i]

        for elem_name, curr_pos in curr.items():
            if elem_name in prev:
                prev_pos = prev[elem_name]
                dx = abs(curr_pos[0] - prev_pos[0])
                dy = abs(curr_pos[1] - prev_pos[1])
                delta = (dx ** 2 + dy ** 2) ** 0.5

                # Detect significant unexpected movement (>5px)
                if delta > 5:
                    shifts.append(LayoutShift(
                        element=elem_name,
                        frame=i,
                        from_pos=prev_pos,
                        to_pos=curr_pos,
                        delta_px=delta
                    ))

    # Calculate stability score (0-100, higher is better)
    max_shift = max([s.delta_px for s in shifts]) if shifts else 0
    shift_penalty = min(len(shifts) * 10, 50)  # Cap at 50
    magnitude_penalty = min(max_shift, 50)  # Cap at 50
    stability_score = max(0, 100 - shift_penalty - magnitude_penalty)

    # Determine verdict
    if stability_score >= 90:
        verdict = 'stable'
    elif stability_score >= 70:
        verdict = 'minor_shifts'
    else:
        verdict = 'unstable'

    return StabilityResult(
        shifts=shifts,
        stability_score=stability_score,
        total_shifts=len(shifts),
        max_shift_px=max_shift,
        verdict=verdict
    )


def test_rapid_interactions(
    action_fn: Callable,
    count: int = 10,
    interval: float = 0.1,
    app_name: str = 'Marcedit',
    freeze_threshold_ms: float = 800.0  # 310ms AS overhead + 500ms actual freeze
) -> Dict[str, Any]:
    """
    Test UI stability under rapid repeated actions.

    Args:
        action_fn: Function that performs the action.
        count: Number of times to repeat.
        interval: Time between actions.
        app_name: Application to test.
        freeze_threshold_ms: Time above which an action is considered a freeze.
            Defaults to 800ms (accounts for ~310ms AppleScript overhead).

    Returns:
        Dict with results of rapid interaction test.
    """
    results = {
        'actions_attempted': count,
        'actions_completed': 0,
        'freezes': [],
        'errors': [],
        'action_times': []
    }

    for i in range(count):
        start = time.perf_counter()

        try:
            action_fn()
            results['actions_completed'] += 1
        except Exception as e:
            results['errors'].append({
                'action': i,
                'error': str(e)
            })

        elapsed_ms = (time.perf_counter() - start) * 1000
        results['action_times'].append(elapsed_ms)

        # Account for AppleScript overhead when detecting freezes
        if elapsed_ms > freeze_threshold_ms:
            results['freezes'].append({
                'action': i,
                'duration_ms': elapsed_ms
            })

        # Check for beach ball
        if detect_beach_ball(app_name):
            results['freezes'].append({
                'action': i,
                'type': 'beach_ball'
            })

        time.sleep(interval)

    # Calculate statistics
    if results['action_times']:
        results['avg_action_time_ms'] = sum(results['action_times']) / len(results['action_times'])
        results['max_action_time_ms'] = max(results['action_times'])
        results['min_action_time_ms'] = min(results['action_times'])

    results['success_rate'] = results['actions_completed'] / count
    results['passed'] = results['success_rate'] >= 0.95 and len(results['freezes']) == 0

    return results


def capture_frame_sequence(
    action_fn: Callable,
    pre_frames: int = 5,
    post_frames: int = 30,
    interval: float = 0.033,
    app_name: str = 'Marcedit',
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Capture screenshot sequence around an action for visual analysis.

    Args:
        action_fn: Function that triggers the action.
        pre_frames: Frames to capture before action.
        post_frames: Frames to capture after action.
        interval: Time between frames.
        app_name: Application to capture.
        output_dir: Directory for frame images.

    Returns:
        Dict with frame paths and timing info.
    """
    import tempfile

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix='gui_frames_')

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    frames = []
    timestamps = []

    # Capture pre-action frames
    for i in range(pre_frames):
        frame_path = output_dir / f'frame_{i:04d}_pre.png'
        observer.capture_window(app_name, str(frame_path))
        frames.append(str(frame_path))
        timestamps.append(time.time())
        time.sleep(interval)

    # Record action time
    action_time = time.time()
    action_fn()

    # Capture post-action frames
    for i in range(post_frames):
        frame_path = output_dir / f'frame_{pre_frames + i:04d}_post.png'
        observer.capture_window(app_name, str(frame_path))
        frames.append(str(frame_path))
        timestamps.append(time.time())
        time.sleep(interval)

    return {
        'output_dir': str(output_dir),
        'frames': frames,
        'frame_count': len(frames),
        'action_frame': pre_frames,
        'timestamps': timestamps,
        'action_time': action_time,
        'interval': interval
    }


def run_responsiveness_suite(app_name: str = 'Marcedit') -> Dict[str, Any]:
    """
    Run comprehensive responsiveness test suite.

    Returns:
        Dict with all test results.
    """
    print(f"Running responsiveness test suite for {app_name}...")

    results = {
        'timestamp': datetime.now().isoformat(),
        'app': app_name,
        'tests': {}
    }

    # Test 1: Basic responsiveness monitoring
    print("  [1/4] Monitoring for freezes (5s)...")
    results['tests']['freeze_monitor'] = monitor_responsiveness(
        duration=5.0,
        interval=0.1,
        app_name=app_name
    )

    # Test 2: Window interaction responsiveness
    print("  [2/4] Testing window click responsiveness...")

    def click_window():
        pos = interactions.get_window_position(app_name)
        if pos:
            interactions.click_at_coordinates(pos[0] + 200, pos[1] + 200, app_name)

    results['tests']['click_response'] = asdict(measure_action_latency(
        action_fn=click_window,
        check_fn=lambda: True,  # Just measure action time
        timeout=2.0
    ))

    # Test 3: Rapid clicking stability
    print("  [3/4] Testing rapid click stability...")
    results['tests']['rapid_clicks'] = test_rapid_interactions(
        action_fn=click_window,
        count=10,
        interval=0.1,
        app_name=app_name
    )

    # Test 4: Layout stability during window interaction
    print("  [4/4] Measuring layout stability...")
    stability = measure_layout_stability(
        action_fn=click_window,
        sample_count=20,
        interval=0.05,
        app_name=app_name
    )
    results['tests']['layout_stability'] = {
        'stability_score': stability.stability_score,
        'total_shifts': stability.total_shifts,
        'max_shift_px': stability.max_shift_px,
        'verdict': stability.verdict,
        'shifts': [asdict(s) for s in stability.shifts[:10]]  # Limit to first 10
    }

    # Overall assessment
    freeze_ok = results['tests']['freeze_monitor']['responsive']
    click_ok = results['tests']['click_response']['responsive']
    rapid_ok = results['tests']['rapid_clicks']['passed']
    layout_ok = stability.verdict in ['stable', 'minor_shifts']

    results['passed'] = all([freeze_ok, click_ok, rapid_ok, layout_ok])
    results['summary'] = {
        'freeze_test': 'PASS' if freeze_ok else 'FAIL',
        'click_test': 'PASS' if click_ok else 'FAIL',
        'rapid_test': 'PASS' if rapid_ok else 'FAIL',
        'layout_test': 'PASS' if layout_ok else 'FAIL'
    }

    print(f"\nResults: {'PASS' if results['passed'] else 'FAIL'}")
    for test, status in results['summary'].items():
        print(f"  {test}: {status}")

    return results


if __name__ == '__main__':
    # Run the test suite
    results = run_responsiveness_suite('Marcedit')

    # Save results
    output_path = Path('/tmp/gui_responsiveness_results.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nDetailed results saved to: {output_path}")
