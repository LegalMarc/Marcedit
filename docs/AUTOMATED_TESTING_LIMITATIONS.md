# Automated Testing Limitations

## Current Status

The Python-based automated test (`test_text_selection_crash.py`) has a critical limitation:

### Problem
**The PDF cannot be loaded automatically into Marcedit** using:
- ❌ AppleScript `open POSIX file` command
- ❌ macOS `open -a Marcedit file.pdf` command
- ❌ AppleScript UI automation (File > Open menu)

### What Works
- ✅ App launches successfully
- ✅ Test PDF is created successfully
- ✅ Window bounds can be detected
- ✅ Mouse clicks can be sent to the window
- ❌ **PDF is never visible in the app window**

### Root Cause
Marcedit may not properly handle:
1. Apple Events for opening files
2. File arguments on launch
3. AppleScript file open commands

## Recommended Approach

### Option 1: Semi-Automated Test (Most Reliable)
```bash
python3 semiautomated_crash_test.py
```
This test:
1. Creates the test PDF
2. Launches Marcedit
3. **Pauses and waits for you to manually open the PDF**
4. Asks you to press Enter when PDF is loaded
5. Automates the click on text
6. Checks for crashes

**This is the most reliable method currently available.**

### Option 2: XCTest (Native UI Testing)
Run via TUI:
```bash
python3 build_tui.py
# Select: 17 (XCTest)
```

XCTest may have better UI automation capabilities than Python/AppleScript.

### Option 3: Manual Testing
1. Launch Marcedit
2. Open any PDF
3. Click on text
4. Check if crash occurs

## Why This Matters

Since the PDF doesn't load automatically:
- The click goes to an empty window
- `startInteractiveFontSearch` is never triggered
- The TextInputUIMacHelper crash never occurs
- **The test gives a FALSE POSITIVE result**

## Next Steps

1. **Fix Marcedit's file opening** to support:
   - Apple Events
   - Command-line file arguments
   - AppleScript open commands

2. **OR use semi-automated testing** with manual PDF opening

3. **OR use XCTest** which may have better integration

## Testing Workaround

Until automated PDF opening works, use:
```bash
python3 semiautomated_crash_test.py
```

This requires manual PDF opening but automates the crash trigger and detection.
