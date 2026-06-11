#!/usr/bin/env python3
"""
UI interaction module using AppleScript accessibility APIs.
Enables Claude to interact with Marcedit UI elements.
"""

import subprocess
import time
from typing import Optional, Tuple, List


def run_applescript(script: str) -> str:
    """Execute AppleScript and return result."""
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True
    )
    if result.returncode != 0 and result.stderr:
        print(f"AppleScript error: {result.stderr}")
    return result.stdout.strip()


def activate_app(app_name: str = 'Marcedit') -> bool:
    """Bring application to front."""
    script = f'tell application "{app_name}" to activate'
    run_applescript(script)
    time.sleep(0.1)
    return True


def click_button(identifier: str, app_name: str = 'Marcedit') -> bool:
    """
    Click a button by accessibility identifier or name.

    Args:
        identifier: Accessibility identifier or button name.
        app_name: Target application.

    Returns:
        True if click succeeded.
    """
    # Try by description (accessibility identifier) first
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            try
                click (first button whose description is "{identifier}")
                return "ok"
            on error
                try
                    click button "{identifier}" of window 1
                    return "ok"
                on error errMsg
                    return "error: " & errMsg
                end try
            end try
        end tell
    end tell
    '''
    result = run_applescript(script)
    return 'ok' in result.lower()


def click_at_coordinates(x: int, y: int, app_name: str = 'Marcedit') -> bool:
    """
    Click at specific coordinates within the application window.

    Args:
        x, y: Coordinates relative to screen.
        app_name: Target application.

    Returns:
        True if click was performed.
    """
    activate_app(app_name)

    script = f'''
    tell application "System Events"
        click at {{{x}, {y}}}
    end tell
    '''
    run_applescript(script)
    return True


def click_in_window(x_offset: int, y_offset: int, app_name: str = 'Marcedit') -> bool:
    """
    Click at offset within the application window.

    Args:
        x_offset, y_offset: Offset from window top-left.
        app_name: Target application.

    Returns:
        True if click was performed.
    """
    # Get window position
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            if (count of windows) > 0 then
                set winPos to position of window 1
                return (item 1 of winPos) & "," & (item 2 of winPos)
            end if
        end tell
    end tell
    return ""
    '''
    result = run_applescript(script)

    if result and ',' in result:
        win_x, win_y = map(int, result.split(','))
        return click_at_coordinates(win_x + x_offset, win_y + y_offset, app_name)

    return False


def type_text(text: str, app_name: str = 'Marcedit') -> bool:
    """
    Type text into the focused field.

    Args:
        text: Text to type.
        app_name: Target application.

    Returns:
        True if typing succeeded.
    """
    activate_app(app_name)

    # Escape special characters for AppleScript
    text = text.replace('\\', '\\\\').replace('"', '\\"')

    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            keystroke "{text}"
        end tell
    end tell
    '''
    run_applescript(script)
    return True


def press_key(key: str, modifiers: List[str] = None, app_name: str = 'Marcedit') -> bool:
    """
    Press a key with optional modifiers.

    Args:
        key: Key to press (e.g., "return", "tab", "escape").
        modifiers: List of modifiers (e.g., ["command", "shift"]).
        app_name: Target application.

    Returns:
        True if key press succeeded.
    """
    activate_app(app_name)

    modifier_str = ""
    if modifiers:
        modifier_str = " using {" + ", ".join(f"{m} down" for m in modifiers) + "}"

    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            key code {get_key_code(key)}{modifier_str}
        end tell
    end tell
    '''
    run_applescript(script)
    return True


def get_key_code(key: str) -> int:
    """Get macOS key code for common keys."""
    key_codes = {
        'return': 36, 'enter': 76, 'tab': 48, 'space': 49,
        'escape': 53, 'delete': 51, 'backspace': 51,
        'up': 126, 'down': 125, 'left': 123, 'right': 124,
        'a': 0, 's': 1, 'd': 2, 'f': 3, 'z': 6, 'x': 7, 'c': 8, 'v': 9,
    }
    return key_codes.get(key.lower(), 0)


def click_menu(menu_name: str, item_name: str, app_name: str = 'Marcedit') -> bool:
    """
    Click a menu item.

    Args:
        menu_name: Name of menu (e.g., "File").
        item_name: Name of menu item (e.g., "Open...").
        app_name: Target application.

    Returns:
        True if click succeeded.
    """
    activate_app(app_name)

    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            click menu item "{item_name}" of menu "{menu_name}" of menu bar 1
        end tell
    end tell
    '''
    result = run_applescript(script)
    return True


def get_window_position(app_name: str = 'Marcedit') -> Optional[Tuple[int, int]]:
    """Get the position of the main window."""
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            if (count of windows) > 0 then
                set winPos to position of window 1
                set xPos to item 1 of winPos as integer
                set yPos to item 2 of winPos as integer
                return (xPos as string) & "," & (yPos as string)
            end if
        end tell
    end tell
    return ""
    '''
    result = run_applescript(script)

    if result and ',' in result:
        try:
            parts = [p.strip() for p in result.split(',')]
            x, y = int(parts[0]), int(parts[1])
            return (x, y)
        except (ValueError, IndexError):
            pass
    return None


def get_window_size(app_name: str = 'Marcedit') -> Optional[Tuple[int, int]]:
    """Get the size of the main window."""
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            if (count of windows) > 0 then
                set winSize to size of window 1
                set wVal to item 1 of winSize as integer
                set hVal to item 2 of winSize as integer
                return (wVal as string) & "," & (hVal as string)
            end if
        end tell
    end tell
    return ""
    '''
    result = run_applescript(script)

    if result and ',' in result:
        try:
            parts = [p.strip() for p in result.split(',')]
            w, h = int(parts[0]), int(parts[1])
            return (w, h)
        except (ValueError, IndexError):
            pass
    return None


def list_ui_elements(app_name: str = 'Marcedit') -> str:
    """
    List all UI elements in the main window.
    Useful for discovering accessibility identifiers.
    """
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            set output to ""
            if (count of windows) > 0 then
                repeat with elem in entire contents of window 1
                    try
                        set elemClass to class of elem as string
                        set elemName to name of elem as string
                        set elemDesc to description of elem as string
                        set output to output & elemClass & ": name='" & elemName & "' desc='" & elemDesc & "'" & linefeed
                    end try
                end repeat
            end if
            return output
        end tell
    end tell
    '''
    return run_applescript(script)


def element_exists(identifier: str, app_name: str = 'Marcedit') -> bool:
    """Check if a UI element exists by identifier."""
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            try
                set elem to first UI element whose description is "{identifier}"
                return true
            on error
                return false
            end try
        end tell
    end tell
    '''
    result = run_applescript(script)
    return result.lower() == 'true'


def is_app_busy(app_name: str = 'Marcedit') -> bool:
    """Check if application is showing busy/wait cursor."""
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            return frontmost and busy status
        end tell
    end tell
    '''
    result = run_applescript(script)
    return 'true' in result.lower()


if __name__ == '__main__':
    # Quick test
    print("Testing UI interactions...")

    # Check if Marcedit is running
    script = 'tell application "System Events" to return name of every process'
    processes = run_applescript(script)

    if 'Marcedit' in processes:
        print("Marcedit is running")

        pos = get_window_position('Marcedit')
        size = get_window_size('Marcedit')
        print(f"Window position: {pos}")
        print(f"Window size: {size}")

        print("\nListing UI elements (first 20 lines):")
        elements = list_ui_elements('Marcedit')
        for line in elements.split('\n')[:20]:
            print(f"  {line}")

        print("\nChecking known identifiers:")
        for ident in ['SaveButton', 'CancelButton', 'PreviewToggle', 'PDFViewer']:
            exists = element_exists(ident)
            print(f"  {ident}: {'Found' if exists else 'Not found'}")
    else:
        print("Marcedit is not running. Launch it first.")
