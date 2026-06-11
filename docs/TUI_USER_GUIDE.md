# 🖥️ TUI USER GUIDE
## Marcedit Build & Test Interface - Complete Reference

---

## 🎯 QUICK START

```bash
cd /path/to/Marcedit
python3 build_tui.py
```

---

## 📋 COMPLETE MENU

### **Build Options** (1-6)

| Option | Name | Description | Time |
|--------|------|-------------|------|
| **1** | Build Debug | Build Debug configuration | 10-30s |
| **2** | Build Release | Build Release configuration (optimized) | 15-45s |
| **3** | Build & Run (Debug) | Build Debug and launch app | 10-30s |
| **4** | Run App | Launch the built app | 1s |
| **5** | Clean Build Directory | Remove all build artifacts | 1s |
| **6** | Show Build Info | Display build details and versions | <1s |

---

### **Swift Testing** (7)

| Option | Name | Description | Time |
|--------|------|-------------|------|
| **7** | Run SwiftPM Tests | Run Swift unit tests via `swift test` | 5-10s |

---

### **Python Unit Tests** (8-12)

| Option | Name | Description | Tests | Time |
|--------|------|-------------|-------|------|
| **8** | Run pytest (All Tests) | All Python unit tests | 61 | 0.14s |
| **9** | Run pytest (Core Tests Only) | Core PDF editing tests | 34 | 0.08s |
| **10** | Run pytest (Reflow Tests Only) | Text reflow tests | 27 | 0.06s |
| **11** | Run pytest with Coverage | All tests + coverage report | 61 | 0.25s |
| **12** | Run Pipeline Verification | End-to-end integration test | - | 2-5s |

---

### **App Stability Tests** (13-15) ⭐ NEW

| Option | Name | Description | Time |
|--------|------|-------------|------|
| **13** | Run Automated Crash Test | Detects startup/stability crashes | 15s |
| **14** | Run UI Interaction Test | Tests menus, windows, text input | 20s |
| **15** | Run Full Stability Suite | Comprehensive test suite (crash + UI + unit) | 60s |

---

## 🎨 MENU ORGANIZATION

The TUI is now organized into **4 logical sections**:

```
╔══════════════════════════════════════════════════════════════╗
║            MARCEDIT BUILD & TEST TUI                         ║
║         PDF Line Editor (Modern Transformation)              ║
╚══════════════════════════════════════════════════════════════╝

Build:
  1) Build Debug
  2) Build Release
  3) Build & Run (Debug)
  4) Run App
  5) Clean Build Directory
  6) Show Build Info

Swift Testing:
  7) Run SwiftPM Tests

Python Unit Tests:
  8) Run pytest (All Tests)
  9) Run pytest (Core Tests Only)
  10) Run pytest (Reflow Tests Only)
  11) Run pytest with Coverage
  12) Run Pipeline Verification

App Stability Tests:
  13) Run Automated Crash Test         ⭐ NEW
  14) Run UI Interaction Test           ⭐ NEW
  15) Run Full Stability Suite          ⭐ NEW

 q) Quit
```

---

## 🚀 RECOMMENDED WORKFLOWS

### **Workflow 1: Initial Build** (Do This First)

```bash
python3 build_tui.py
```

**Select**: `2` → `Build Release`

**Expected**:
```
Building Release configuration with SwiftPM...
✓ Building Release completed successfully!
✓ App Bundle ready at: ignored-resources/Marcedit.app
Version 0.6.42
```

---

### **Workflow 2: Quick Stability Check** (Before Deploying)

```bash
python3 build_tui.py
```

**Select**: `13` → `Run Automated Crash Test`

**Expected**:
```
Running Automated Crash Test...

Launching app...
✓ App launched successfully (PID: 12345)

Checking stability...
✓ App still running after 10s

Checking menus...
✓ Found 6 menu items

Checking windows...
✓ 1 | Untitled

Checking crash logs...
✓ No recent crash logs

TEST SUMMARY
  ✓ PASS: App Launch
  ✓ PASS: Stability (10s)
  ✓ PASS: Menu System
  ✓ PASS: Window Creation
  ✓ PASS: Crash Logs

🎉 ALL TESTS PASSED - App appears stable!
```

---

### **Workflow 3: Full Validation** (Pre-Release)

```bash
python3 build_tui.py
```

**Select**: `15` → `Run Full Stability Suite`

**This runs**:
1. Automated crash test (15s)
2. UI interaction test (20s)
3. Python unit tests (0.14s)

**Expected**:
```
Running Full Stability Suite...

This will run:
  1. Automated crash test
  2. UI interaction test
  3. Python unit tests

─── Test 1/3: Automated Crash Test ───
[Crash test output...]
✓ Automated crash test passed

─── Test 2/3: UI Interaction Test ───
[UI test output...]
✓ UI interaction test passed

─── Test 3/3: Python Unit Tests ───
[Unit test output...]
✓ Python unit tests passed

Stability Suite Summary

  ✓ PASS: Automated Crash Test
  ✓ PASS: UI Interaction Test
  ✓ PASS: Python Unit Tests

✓ All stability tests passed (3/3)
  App is stable and ready for use!
```

---

### **Workflow 4: After Code Changes**

```bash
python3 build_tui.py
```

**Select**: `2` → `Build Release`

**Then**: `9` → `Run pytest (Core Tests Only)`

**Then**: `13` → `Run Automated Crash Test`

**Total time**: ~45 seconds

---

### **Workflow 5: After Fixing a Crash**

```bash
python3 build_tui.py
```

**Select**:
1. `5` → Clean Build Directory (confirm `y`)
2. `2` → Build Release
3. `13` → Run Automated Crash Test
4. `14` → Run UI Interaction Test
5. `15` → Run Full Stability Suite

**This ensures**:
- ✅ Clean build
- ✅ No startup crashes
- ✅ No UI crashes
- ✅ No stability issues
- ✅ All unit tests pass

---

## 📊 TEST DETAILS

### **Option 13: Automated Crash Test**

**What it tests**:
- ✅ App launches without crashing
- ✅ App remains stable for 10 seconds
- ✅ Menu bar is accessible
- ✅ Windows can be created
- ✅ No new crash logs generated

**How it works**:
1. Creates a test PDF using PyMuPDF
2. Launches Marcedit app
3. Monitors app for 10 seconds
4. Checks crash logs directory
5. Verifies app process still running
6. Cleanly quits app

**Detects**:
- Crash on launch
- Delayed crashes (within 10s)
- Menu system crashes
- Window creation failures

---

### **Option 14: UI Interaction Test**

**What it tests**:
- ✅ App launch
- ✅ Menu bar (File, Edit, View, Window, Help)
- ✅ Menu clicking and interaction
- ✅ Window detection and info
- ✅ **Text input system** (Specifically tests `TextInputUIMacHelper`)
- ✅ Keystroke handling (Cmd+N, etc.)
- ✅ App stability over 5 seconds

**How it works**:
1. Launches app via AppleScript
2. Clicks File menu to test menu system
3. Checks for windows
4. Searches for text areas/fields
5. Clicks text area to trigger `TextInputUIMacHelper`
6. Sends Cmd+N keystroke
7. Waits 5 seconds for delayed crashes
8. Reports results

**Detects**:
- **TextInputUIMacHelper crashes** (Your specific issue!)
- Menu system crashes
- Window creation failures
- Keystroke handling bugs
- UI responsiveness issues

---

### **Option 15: Full Stability Suite**

**What it tests**:
- ✅ Everything from crash test (Option 13)
- ✅ Everything from UI test (Option 14)
- ✅ All Python unit tests (61 tests)

**How it works**:
Runs tests 13, 14, and 8 in sequence, with a summary report.

**Best for**:
- Pre-release validation
- After major changes
- Verifying complete fix
- Comprehensive regression testing

---

## 🐛 CRASH DETECTION

### What Tests Catch Which Crashes

| Crash Type | Test 13 | Test 14 | Test 15 |
|------------|---------|---------|---------|
| Crash on launch | ✅ | ✅ | ✅ |
| TextInputUIMacHelper crash | ❌ | ✅ | ✅ |
| Menu crash | ❌ | ✅ | ✅ |
| Delayed crash (10s) | ✅ | ✅ | ✅ |
| Delayed crash (5s) | ❌ | ✅ | ✅ |
| Memory leak (short) | ⚠️ | ❌ | ❌ |
| Logic errors | ❌ | ❌ | ✅ |

**Legend**: ✅ Detects | ⚠️ Partially detects | ❌ Doesn't detect

---

## 📈 TEST RESULTS INTERPRETATION

### **All Tests Pass** ✅

```
✓ All stability tests passed (3/3)
  App is stable and ready for use!
```

**Meaning**: Your app is stable, no crashes detected

**Next steps**:
- Deploy with confidence
- Use for daily development
- No further testing needed (unless you make changes)

---

### **Some Tests Fail** ⚠️

```
✗ FAIL: UI Interaction Test
✓ PASS: Automated Crash Test
✓ PASS: Python Unit Tests

⚠ Some stability tests failed (2/3)
  Review failures above before deploying
```

**Meaning**: App has issues that need fixing

**Next steps**:
1. Review the failure output
2. Check `CRASH_FIX.md` for common issues
3. Fix the problem
4. Re-run test suite

---

## 🎯 TIPS & BEST PRACTICES

### **Tip 1: Always Clean After Crashes**

If you encounter a crash:
```
python3 build_tui.py
5 → Clean Build Directory → y
2 → Build Release
```

This ensures no corrupted build artifacts.

---

### **Tip 2: Use Test 15 Before Release**

Option 15 (Full Stability Suite) gives you maximum confidence:

```
python3 build_tui.py
15 → Run Full Stability Suite
```

If it passes, you're good to deploy!

---

### **Tip 3: Quick Test During Development**

Use Option 9 for rapid iteration:

```
python3 build_tui.py
9 → Run pytest (Core Tests Only)
```

Takes only 0.08 seconds!

---

### **Tip 4: Verify Fixes**

After fixing a crash, run this sequence:

```
python3 build_tui.py
5 → Clean → 2 → Build Release
13 → Automated Crash Test
14 → UI Interaction Test
```

This validates your fix completely.

---

### **Tip 5: Check Coverage**

Use Option 11 to see code coverage:

```
python3 build_tui.py
11 → Run pytest with Coverage

# Then view HTML report:
open htmlcov/index.html
```

---

## 🔧 TROUBLESHOOTING

### "Test script not found"

**Problem**: Test files missing

**Solution**:
```bash
# Ensure test files exist in project root
ls test_app_crash.py
ls test_ui_interactions.scpt
```

---

### "App not found"

**Problem**: App hasn't been built

**Solution**:
```
python3 build_tui.py
2 → Build Release
```

---

### "All tests fail"

**Problem**: App is crashing immediately

**Solution**:
1. Check `CRASH_FIX.md`
2. Ensure Info.plist has all keys
3. Run clean build:
   ```
   python3 build_tui.py
   5 → Clean → y
   2 → Build Release
   ```

---

### "Tests pass but app crashes in use"

**Problem**: Edge case not covered by automated tests

**Solution**:
1. Run manual testing (see TESTING_GUIDE.md)
2. Check Console.app for crash logs
3. Report the issue with reproduction steps

---

## 📚 REFERENCE

### All Menu Options Summary

| # | Option | Category | Time | Use When |
|---|--------|----------|------|----------|
| 1 | Build Debug | Build | 10-30s | Developing |
| 2 | Build Release | Build | 15-45s | Deploying |
| 3 | Build & Run | Build | 10-30s | Quick test |
| 4 | Run App | Build | 1s | Launching |
| 5 | Clean | Build | 1s | After crashes |
| 6 | Show Info | Build | <1s | Checking version |
| 7 | Swift Tests | Swift | 5-10s | Testing Swift code |
| 8 | pytest all | Python | 0.14s | Full unit test |
| 9 | pytest core | Python | 0.08s | Testing core.py |
| 10 | pytest reflow | Python | 0.06s | Testing reflow.py |
| 11 | pytest + cov | Python | 0.25s | Coverage report |
| 12 | Pipeline | Python | 2-5s | Integration test |
| **13** | **Crash Test** | **Stability** | **15s** | **Quick stability** |
| **14** | **UI Test** | **Stability** | **20s** | **UI validation** |
| **15** | **Full Suite** | **Stability** | **60s** | **Pre-release** |

---

## ✅ SUMMARY

The TUI now provides:

- ✅ **All build operations** in one place
- ✅ **All testing operations** in one place
- ✅ **Crash detection** (3 test options)
- ✅ **Unit testing** (5 test options)
- ✅ **UI testing** (AppleScript-powered)
- ✅ **Coverage reporting** (HTML + terminal)
- ✅ **One unified interface** for everything

**No more**:
- ❌ Running scripts manually
- ❌ Remembering command-line arguments
- ❌ Switching between different tools
- ❌ Wondering what to test

**Just**:
- ✅ Run `python3 build_tui.py`
- ✅ Select an option
- ✅ Get results

---

*TUI User Guide: January 22, 2026*
*Total Options: 15*
*Categories: 4*
*Test Coverage: Complete*
