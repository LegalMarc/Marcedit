# Testing Guide - Architecture V2

**Purpose:** How to test the new Architecture V2 implementation
**Status:** Week 1 Complete - Ready for Manual Testing
**Last Updated:** 2026-01-23

---

## 🧪 Testing Overview

Since Week 1 focused on architecture and PDFOperationsBridge is stubbed, we can test:
- ✅ **State management** - DocumentCoordinator operations
- ✅ **Feature flags** - Toggle V2 on/off
- ✅ **Type safety** - Compilation validates types
- ✅ **State machine** - Transition validation
- ⏳ **PDF operations** - Will be testable after Week 2

---

## 🚀 Quick Start Testing

### 1. Verify Clean Build

```bash
cd /path/to/Marcedit
swift package clean
swift build
```

**Expected:** Build complete in ~8 seconds with 0 errors

### 2. Run the Application

```bash
swift run
```

**Expected:** App launches with old architecture (V2 disabled by default)

### 3. Enable V2 Architecture (Code)

Edit `Sources/Marcedit/MarceditApp.swift`:

```swift
@main
struct MarceditApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    init() {
        #if DEBUG
        // Enable all V2 features for testing
        FeatureFlags.enableAllV2Features()
        print("=== Architecture V2 Enabled ===")
        print(FeatureFlags.getStatusSummary())
        #endif
    }

    var body: some Scene {
        // ...
    }
}
```

### 4. Update ContentView to Use V2

Edit `Sources/Marcedit/ContentView.swift`:

```swift
struct ContentView: View {
    // OLD: @StateObject private var vm = EditorViewModel()

    // NEW: Use V2 architecture
    @StateObject private var vm = EditorViewModelV2(useNewArchitecture: true)

    var body: some View {
        // Existing view code works unchanged!
    }
}
```

**Build and run again:**
```bash
swift build && swift run
```

---

## 📋 Manual Test Cases

### Test 1: Feature Flag Verification

**Steps:**
1. Enable V2 via code (as shown above)
2. Run app and check console output

**Expected Output:**
```
=== Architecture V2 Enabled ===
Feature Flags Status:
- DocumentCoordinator: true
- NewFontMatcher: true
- AtomicFileOps: true
- CommandUndo: true
- StateMachine: true
- XPCPythonService: false
- VisualTesting: false
```

**Pass Criteria:** All V2 flags show `true`

---

### Test 2: State Management (Document Opening)

**Steps:**
1. Run app with V2 enabled
2. Drag a PDF file into the app
3. Check console logs

**Expected Console Output:**
```
[DocumentCoordinator] Initialized
[FileManagerService] Creating working copy of: sample.pdf
[DocumentCoordinator] Opening document: <UUID>
[DocumentCoordinator] Document opened successfully
```

**Pass Criteria:**
- No crashes
- Console shows DocumentCoordinator logs
- Document appears in UI

**Note:** Actual PDF operations will stub out (expected behavior until Week 2)

---

### Test 3: Feature Flag Toggle

**Steps:**
1. Run app with V2 enabled
2. Open Settings → Developer → Feature Flags (if Settings UI exists)
3. Toggle individual flags
4. Check `FeatureFlags.getStatusSummary()`

**Alternative (Programmatic):**
```swift
// In a test view or debug menu
Button("Disable V2") {
    FeatureFlags.disableAllV2Features()
    print(FeatureFlags.getStatusSummary())
}

Button("Enable V2") {
    FeatureFlags.enableAllV2Features()
    print(FeatureFlags.getStatusSummary())
}
```

**Pass Criteria:**
- Flags toggle correctly
- Status summary reflects changes
- No crashes

---

### Test 4: ViewModel Compatibility

**Steps:**
1. Enable V2 architecture
2. Open a PDF
3. Try existing UI interactions:
   - Select text
   - Open edit dialog
   - Modify text
   - Attempt save

**Expected Behavior:**
- UI interactions work (text selection, dialog opening)
- Edit operations stub out gracefully
- Console shows: `"PDFOperationsBridge: replaceText() not yet implemented - throwing error"`
- Error message displays in UI
- No crashes

**Pass Criteria:**
- UI remains responsive
- Errors are handled gracefully
- Old functionality continues to work with V1 fallback

---

### Test 5: State Machine Validation

**Steps:**
1. Enable V2 architecture
2. Trigger state transitions:
   - Idle → Select text → Detecting
   - Detecting → Font detected → Editing
   - Editing → Start search → Searching
   - Editing → Replace → Validating

**Test Invalid Transitions:**
```swift
// Try invalid transition (should throw error)
let stateMachine = EditSessionStateMachine()
do {
    // Can't replace from idle state
    _ = try stateMachine.transition(action: .replace)
    // Should not reach here
    XCTFail("Should have thrown invalid transition error")
} catch EditSessionStateMachine.StateMachineError.invalidTransition {
    // Expected error
    print("✓ Invalid transition correctly rejected")
}
```

**Pass Criteria:**
- Valid transitions succeed
- Invalid transitions throw errors
- No crashes from state machine

---

### Test 6: Actor Isolation (Concurrency Safety)

**Steps:**
1. Enable V2 architecture
2. Open multiple PDFs concurrently
3. Perform operations on different documents simultaneously

**Test Code:**
```swift
func testConcurrentDocumentOperations() async throws {
    let coordinator = DocumentCoordinator(
        fileManager: try FileManagerService(),
        fontMatcher: FontMatcherService(),
        pdfOperations: PDFOperationsBridge()
    )

    // Open 10 documents concurrently
    await withTaskGroup(of: Void.self) { group in
        for i in 0..<10 {
            group.addTask {
                do {
                    let url = URL(fileURLWithPath: "/path/to/test\(i).pdf")
                    _ = try await coordinator.openDocument(at: url)
                    print("✓ Document \(i) opened")
                } catch {
                    print("✗ Document \(i) failed: \(error)")
                }
            }
        }
    }

    print("✓ All concurrent operations completed without crashes")
}
```

**Pass Criteria:**
- No data races (run with Thread Sanitizer)
- No crashes
- All operations complete
- Actor properly serializes access

---

### Test 7: Memory Management

**Steps:**
1. Enable V2 architecture
2. Open and close 100 documents in sequence
3. Monitor memory usage with Instruments

**Test Code:**
```swift
func testMemoryManagement() async throws {
    let coordinator = DocumentCoordinator(...)

    for i in 0..<100 {
        let url = URL(fileURLWithPath: "/path/to/test.pdf")
        let state = try await coordinator.openDocument(at: url)
        try await coordinator.closeDocument(id: state.id)

        if i % 10 == 0 {
            print("Processed \(i) documents")
        }
    }

    print("✓ Memory test complete")
}
```

**Expected:**
- Memory usage remains stable
- Working copies cleaned up
- No memory leaks in Instruments
- Font cache properly evicts (max 100 entries)

**Pass Criteria:**
- Memory < 200MB throughout test
- No leaks detected
- Cache eviction working

---

### Test 8: Feature Flag Rollback

**Steps:**
1. Enable V2 architecture
2. Open a PDF (will use V2)
3. Disable V2 features: `FeatureFlags.disableAllV2Features()`
4. Restart app
5. Open same PDF (should use V1)

**Pass Criteria:**
- V2 → V1 transition is clean
- No data loss
- No crashes
- V1 functionality restored

---

### Test 9: Type Safety Validation

**This is tested at compile time!**

**Examples of type safety:**
```swift
// ✅ Compile-time validated
let request = ReplaceTextRequest(
    targetText: "Hello",
    replacementText: "Goodbye",
    pageIndex: 0,
    overrides: TextOverrides(),
    detectedFont: nil,
    targetRect: CGRect.zero
)

// ❌ Won't compile - type mismatch
let badRequest = ReplaceTextRequest(
    targetText: 123,  // Error: Cannot convert Int to String
    // ...
)

// ✅ Codable protocol ensures serializability
let data = try JSONEncoder().encode(request)
let decoded = try JSONDecoder().decode(ReplaceTextRequest.self, from: data)
```

**Pass Criteria:**
- All Codable types serialize/deserialize correctly
- Type mismatches caught at compile time
- No runtime type errors

---

## 🔍 Debugging Tips

### Enable Verbose Logging

Add to each service:
```swift
private let logger = Logger(subsystem: "com.marcedit.app", category: "SERVICE_NAME")

// Set log level
logger.log(level: .debug, "Detailed debug info")
logger.info("Important info")
logger.warning("Warning message")
logger.error("Error occurred")
```

### View Logs
```bash
# Console.app - Filter by "com.marcedit.app"
# Or use command line:
log stream --predicate 'subsystem == "com.marcedit.app"' --level debug
```

### Debug Actor State

```swift
// Print actor state (in async context)
Task {
    if let state = await coordinator.getState(for: docID) {
        print("Current URL: \(state.currentURL)")
        print("Is dirty: \(state.isDirty)")
        print("Undo stack: \(state.undoStack.count)")
        print("Redo stack: \(state.redoStack.count)")
    }
}
```

### Monitor Feature Flags

```swift
// Add observer for flag changes
NotificationCenter.default.addObserver(
    forName: UserDefaults.didChangeNotification,
    object: nil,
    queue: .main
) { _ in
    print(FeatureFlags.getStatusSummary())
}
```

---

## ⚠️ Known Limitations (Week 1)

### PDFOperationsBridge is Stubbed

**These operations will fail gracefully:**
- `replaceText()` → throws `.notImplemented`
- `identifyFont()` → returns hardcoded Helvetica
- `createMemento()` → returns stub memento
- `restoreFromMemento()` → uses backup file fallback

**Expected Behavior:**
- Operations throw descriptive errors
- UI shows error message
- App doesn't crash
- Can continue using old architecture

**Timeline:** Full implementation in Week 2

### No Visual Regression Tests

**Current Testing:** Manual visual inspection only
**Timeline:** Automated tests in Week 4

### No Performance Benchmarks

**Current Testing:** Architecture is ready, but stubs don't demonstrate performance
**Timeline:** Real performance validation after Week 2

---

## 📊 Test Coverage Matrix

| Component | Unit Tests | Integration Tests | Manual Tests |
|-----------|-----------|-------------------|--------------|
| DocumentCoordinator | Week 4 | Week 4 | ✅ Available |
| EditCommand | Week 4 | Week 4 | ✅ Available |
| EditSessionStateMachine | Week 4 | Week 4 | ✅ Available |
| FileManagerService | Week 4 | Week 4 | ✅ Available |
| FontMatcherService | Week 4 | Week 4 | ✅ Available |
| PDFOperationsBridge | Week 4 | Week 2+ | ⏳ Stubbed |
| EditorViewModelV2 | Week 4 | Week 4 | ✅ Available |
| FeatureFlags | Week 4 | Week 4 | ✅ Available |

---

## 🧰 Testing Tools

### Thread Sanitizer (Detect Data Races)

```bash
swift build -Xswiftc -sanitize=thread
swift test -Xswiftc -sanitize=thread
```

### Address Sanitizer (Detect Memory Issues)

```bash
swift build -Xswiftc -sanitize=address
swift test -Xswiftc -sanitize=address
```

### Instruments (Performance & Memory)

1. Open Xcode
2. Product → Profile
3. Select Instrument:
   - **Leaks** - Memory leak detection
   - **Allocations** - Memory usage tracking
   - **Time Profiler** - CPU usage

### Console.app (View Logs)

1. Open Console.app
2. Filter: `subsystem:com.marcedit.app`
3. Set Action: Start streaming
4. Run app

---

## ✅ Pre-Week 2 Checklist

Before starting Week 2 implementation:

- [ ] Week 1 code compiles without errors ✅ (Already done)
- [ ] Feature flags toggle correctly
- [ ] DocumentCoordinator opens/closes documents
- [ ] State machine validates transitions
- [ ] EditorViewModelV2 forwards to coordinator
- [ ] No crashes with V2 enabled
- [ ] Graceful degradation when operations stubbed
- [ ] Memory usage stable
- [ ] Old architecture still works (V2 disabled)

---

## 🎯 Success Criteria

### Week 1 Manual Testing

**Goal:** Verify architecture is solid, even with stubbed operations

**Success Indicators:**
1. ✅ App launches with V2 enabled
2. ✅ Feature flags work correctly
3. ✅ State management functions
4. ✅ No crashes or data races
5. ✅ Graceful error handling for stubs
6. ✅ Memory management works
7. ✅ Can rollback to V1
8. ✅ Type safety enforced

**If any fail:** Fix before proceeding to Week 2

---

## 📝 Test Results Template

```markdown
## Test Session: [Date]

**Tester:** [Name]
**Build:** [Commit hash]
**Configuration:** V2 Enabled: [Yes/No]

### Test Results

| Test Case | Status | Notes |
|-----------|--------|-------|
| Feature Flag Verification | ✅ Pass | All flags enabled correctly |
| State Management | ✅ Pass | Documents open/close cleanly |
| Feature Flag Toggle | ✅ Pass | Toggles work, no crashes |
| ViewModel Compatibility | ⚠️ Partial | Stubs behave as expected |
| State Machine Validation | ✅ Pass | Invalid transitions rejected |
| Actor Isolation | ✅ Pass | No data races detected |
| Memory Management | ✅ Pass | Stable at 150MB |
| Feature Flag Rollback | ✅ Pass | Clean V2→V1 transition |
| Type Safety | ✅ Pass | Compiles correctly |

### Issues Found

1. [Issue description]
   - Severity: [Low/Medium/High/Critical]
   - Steps to reproduce: [...]
   - Expected: [...]
   - Actual: [...]

### Recommendations

- [Recommendation 1]
- [Recommendation 2]

### Next Steps

- [ ] Fix identified issues
- [ ] Retest failed cases
- [ ] Proceed to Week 2
```

---

## 🚀 Ready for Week 2?

After completing manual testing and verifying all success criteria:

1. ✅ Document test results
2. ✅ Fix any critical issues
3. ✅ Review `WEEK2_ROADMAP.md`
4. 🚀 Begin XPC Python Service implementation

---

**Happy Testing!** 🧪

---

**Created:** 2026-01-23
**For:** Architecture V2 Week 1
**Next:** Week 2 Integration Testing (after XPC implementation)
