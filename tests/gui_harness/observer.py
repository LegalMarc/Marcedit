#!/usr/bin/env python3
"""
Screenshot capture and visual observation module.
Enables Claude to "see" the Marcedit UI.
"""

import subprocess
import tempfile
import time
import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple


def capture_screenshot(output_path: Optional[str] = None) -> Path:
    """
    Capture full screen screenshot.

    Args:
        output_path: Optional path for screenshot. Auto-generated if None.

    Returns:
        Path to screenshot PNG file.
    """
    if os.environ.get("MARCEDIT_ALLOW_FULLSCREEN_CAPTURE") != "1":
        raise RuntimeError("Set MARCEDIT_ALLOW_FULLSCREEN_CAPTURE=1 to enable full-screen capture")

    if output_path is None:
        output_path = tempfile.mktemp(suffix='.png', prefix='gui_screenshot_')

    output = Path(output_path)
    subprocess.run(['screencapture', '-x', str(output)], check=True)
    return output


def capture_window(app_name: str = 'Marcedit', output_path: Optional[str] = None) -> Path:
    """
    Capture screenshot of specific application window.

    Args:
        app_name: Name of application to capture.
        output_path: Optional path for screenshot.

    Returns:
        Path to screenshot PNG file.
    """
    if output_path is None:
        output_path = tempfile.mktemp(suffix='.png', prefix=f'{app_name}_')

    output = Path(output_path)

    # Activate app first to ensure it's visible
    activate_app(app_name)
    time.sleep(0.2)

    # Get window bounds via AppleScript
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            if (count of windows) > 0 then
                set winPos to position of window 1
                set winSize to size of window 1
                return (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winSize) & "," & (item 2 of winSize)
            end if
        end tell
    end tell
    return ""
    '''
    result = run_applescript(script)

    if result and ',' in result:
        try:
            x, y, w, h = map(int, result.split(','))
            # Use region capture: -R x,y,w,h
            subprocess.run(['screencapture', '-x', '-R', f'{x},{y},{w},{h}', str(output)], check=True)
            return output
        except (ValueError, subprocess.CalledProcessError):
            pass

    if os.environ.get("MARCEDIT_ALLOW_FULLSCREEN_CAPTURE") != "1":
        raise RuntimeError("Window capture failed and full-screen fallback is disabled")

    subprocess.run(['screencapture', '-x', str(output)], check=True)
    return output


def get_window_id(app_name: str) -> Optional[int]:
    """Get the window ID for an application."""
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            if (count of windows) > 0 then
                return id of window 1
            end if
        end tell
    end tell
    return ""
    '''
    result = run_applescript(script)
    try:
        return int(result) if result else None
    except ValueError:
        return None


def activate_app(app_name: str) -> bool:
    """Bring application to front."""
    script = f'tell application "{app_name}" to activate'
    run_applescript(script)
    return True


def run_applescript(script: str) -> str:
    """Execute AppleScript and return result."""
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()


def capture_window_hash(app_name: str = 'Marcedit') -> str:
    """
    Capture window and return hash for quick comparison.
    Useful for detecting if UI has changed.
    """
    screenshot = capture_window(app_name)
    with open(screenshot, 'rb') as f:
        content = f.read()
    screenshot.unlink()  # Clean up
    return hashlib.md5(content).hexdigest()


def rapid_capture(app_name: str = 'Marcedit', count: int = 30, interval: float = 0.033,
                  output_dir: Optional[str] = None) -> list:
    """
    Capture rapid sequence of screenshots (like video frames).

    Args:
        app_name: Application to capture.
        count: Number of frames to capture.
        interval: Time between frames (0.033 = ~30fps).
        output_dir: Directory for frame images.

    Returns:
        List of paths to frame images.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix='gui_frames_')

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    frames = []
    window_id = get_window_id(app_name)

    for i in range(count):
        frame_path = output_dir / f'frame_{i:04d}.png'

        if window_id:
            subprocess.run(['screencapture', '-x', '-l', str(window_id), str(frame_path)])
        else:
            subprocess.run(['screencapture', '-x', str(frame_path)])

        frames.append(frame_path)
        time.sleep(interval)

    return frames


def compare_screenshots(path1: Path, path2: Path) -> dict:
    """
    Compare two screenshots and return difference metrics.

    Returns:
        {identical: bool, hash_diff: int, pixel_diff_estimate: float}
    """
    with open(path1, 'rb') as f:
        hash1 = hashlib.md5(f.read()).hexdigest()
    with open(path2, 'rb') as f:
        hash2 = hashlib.md5(f.read()).hexdigest()

    identical = hash1 == hash2

    # Count differing hex chars as rough similarity measure
    diff_chars = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

    return {
        'identical': identical,
        'hash1': hash1,
        'hash2': hash2,
        'hash_diff_chars': diff_chars,
        'similarity': 1.0 - (diff_chars / 32)  # MD5 has 32 hex chars
    }


if __name__ == '__main__':
    # Quick test
    print("Testing screenshot capture...")

    # Check if Marcedit is running
    script = 'tell application "System Events" to return name of every process'
    processes = run_applescript(script)

    if 'Marcedit' in processes:
        print("Marcedit is running, capturing window...")
        path = capture_window('Marcedit')
        print(f"Screenshot saved to: {path}")

        # Test hash capture
        print("Testing rapid hash comparison...")
        hash1 = capture_window_hash('Marcedit')
        time.sleep(0.5)
        hash2 = capture_window_hash('Marcedit')
        print(f"Hash identical: {hash1 == hash2}")
    else:
        print("Marcedit is not running. Launch it first.")
