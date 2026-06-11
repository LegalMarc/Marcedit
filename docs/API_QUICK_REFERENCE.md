# Architecture V2 - API Quick Reference

**Version:** 1.0
**Last Updated:** 2026-01-24
**Status:** Week 4 Day 3

---

## 📚 Quick Navigation

- [DocumentCoordinator](#documentcoordinator) - Central state management
- [FileManagerService](#filemanagerservice) - File & transaction operations
- [PDFOperationsBridge](#pdfoperationsbridge) - Python PDF operations
- [FontMatcherService](#fontmatcherservice) - Font matching
- [FeatureFlags](#featureflags) - Feature flag system
- [Testing Infrastructure](#testing-infrastructure) - Test utilities

---

## DocumentCoordinator

**Purpose:** Central actor for all document state management
**File:** `Sources/Marcedit/Architecture/DocumentCoordinator.swift`
**Thread-Safe:** ✅ Actor-isolated

### Document Lifecycle

```swift
actor DocumentCoordinator {
    // Open document
    func openDocument(at url: URL) async throws -> DocumentState

    // Close document
    func closeDocument(id: UUID) async throws

    // Select document
    func selectDocument(id: UUID) throws

    // Get document state
    func getState(for id: UUID) -> DocumentState?

    // Get selected document ID
    func getSelectedDocumentID() -> UUID?
}
```

**Example:**
```swift
let coordinator = DocumentCoordinator(
    fileManager: FileManagerService(),
    pdfOperations: PDFOperationsBridge(),
    fontMatcher: FontMatcherService()
)

// Open document
let docState = try await coordinator.openDocument(at: pdfURL)
let docID = docState.id

// Get state
if let state = await coordinator.getState(for: docID) {
    print("Current URL: \(state.currentURL)")
    print("Undo count: \(state.undoStack.count)")
}

// Close when done
try await coordinator.closeDocument(id: docID)
```

### Edit Sessions

```swift
// Begin edit session
func beginEditSession(
    for documentID: UUID,
    page pageIndex: Int,
    textBounds: CGRect
) async throws

// End edit session
func endEditSession(documentID: UUID) throws
```

**Example:**
```swift
try await coordinator.beginEditSession(
    for: docID,
    page: 0,
    textBounds: CGRect(x: 100, y: 200, width: 300, height: 50)
)

// ... perform edits ...

try coordinator.endEditSession(documentID: docID)
```

### Font Search

```swift
func startFontSearch(
    for documentID: UUID,
    targetFont: FontDescriptor
) async -> AsyncStream<FontSearchProgress>

func getFontSearchResults(for documentID: UUID) async -> [FontSearchResult]?
```

**Example:**
```swift
let targetFont = FontDescriptor(
    family: "Helvetica",
    postscriptName: "Helvetica",
    weight: 400,
    width: .normal,
    slant: .upright,
    size: 12.0,
    xHeight: nil,
    capHeight: nil,
    ascender: nil,
    descender: nil
)

let progressStream = await coordinator.startFontSearch(
    for: docID,
    targetFont: targetFont
)

for await progress in progressStream {
    switch progress {
    case .started(let totalFonts):
        print("Searching \(totalFonts) fonts...")
    case .progress(let current, let total):
        print("Progress: \(current)/\(total)")
    case .completed(let results):
        print("Found \(results.count) matching fonts")
        break
    case .failed(let error):
        print("Search failed: \(error)")
        break
    }
}
```

### Undo/Redo

```swift
func executeCommand(_ command: any EditCommand) async throws
func undo(documentID: UUID) async throws
func redo(documentID: UUID) async throws
```

**Example:**
```swift
let command = ReplaceTextCommand(
    documentID: docID,
    pageIndex: 0,
    originalText: "Hello",
    replacementText: "Hi",
    textBounds: CGRect(x: 100, y: 200, width: 100, height: 20),
    overrides: nil
)

try await coordinator.executeCommand(command)

// Undo
try await coordinator.undo(documentID: docID)

// Redo
try await coordinator.redo(documentID: docID)
```

### Document State

```swift
struct DocumentState: Sendable {
    let id: UUID
    let originalURL: URL
    var currentURL: URL
    var isDirty: Bool
    var md5Checksum: String?
    var editSession: EditSession?
    var fontSearchCache: [String: FontSearchCacheEntry]
    var undoStack: [any EditCommand]
    var redoStack: [any EditCommand]
    var pdfScaleFactor: Double
    var currentPage: Int
}
```

---

## FileManagerService

**Purpose:** ACID transaction-based file operations
**File:** `Sources/Marcedit/Services/FileManagerService.swift`
**Thread-Safe:** ✅ Actor-isolated

### Transaction Operations

```swift
actor FileManagerService {
    // Begin transaction
    func beginTransaction(for url: URL) async throws -> UUID

    // Get working URL for transaction
    func getWorkingURL(for transactionID: UUID) async -> URL?

    // Commit transaction
    func commitTransaction(_ transactionID: UUID) async throws

    // Rollback transaction
    func rollbackTransaction(_ transactionID: UUID) async throws
}
```

**Example:**
```swift
let fileManager = FileManagerService()

// Begin transaction
let txID = try await fileManager.beginTransaction(for: pdfURL)

// Get working copy URL
guard let workingURL = await fileManager.getWorkingURL(for: txID) else {
    throw Error("No working URL")
}

// Modify working copy
try modifyPDF(at: workingURL)

// Commit (atomic swap)
try await fileManager.commitTransaction(txID)

// OR rollback if error
// try await fileManager.rollbackTransaction(txID)
```

### Checksum Operations

```swift
// Calculate SHA256 checksum
static func calculateChecksum(url: URL) async throws -> String
```

**Example:**
```swift
let checksum = try await FileManagerService.calculateChecksum(url: pdfURL)
print("SHA256: \(checksum)")
```

### Atomic File Operations

```swift
// Atomic copy with coordinator
static func atomicCopy(from source: URL, to destination: URL) async throws

// Atomic move with coordinator
static func atomicMove(from source: URL, to destination: URL) async throws
```

---

## PDFOperationsBridge

**Purpose:** Bridge to Python PDF operations via XPC
**File:** `Sources/Marcedit/Services/PDFOperationsBridge.swift`
**Thread-Safe:** ✅ Actor-isolated

### Font Operations

```swift
actor PDFOperationsBridge {
    // Identify font at location
    func identifyFont(
        documentURL: URL,
        pageIndex: Int,
        targetText: String
    ) async throws -> FontDescriptor

    // Match font from descriptor
    func matchFont(
        targetDescriptor: FontDescriptor
    ) async throws -> [FontSearchResult]
}
```

**Example:**
```swift
let pdfOps = PDFOperationsBridge()

// Identify font
let font = try await pdfOps.identifyFont(
    documentURL: pdfURL,
    pageIndex: 0,
    targetText: "Hello World"
)

print("Font: \(font.family) \(font.weight)")
```

### Text Operations

```swift
// Replace text
func replaceText(
    documentURL: URL,
    pageIndex: Int,
    textBounds: CGRect,
    originalText: String,
    replacementText: String,
    overrides: [String: Any]
) async throws -> ReplaceTextResult
```

**Example:**
```swift
let result = try await pdfOps.replaceText(
    documentURL: pdfURL,
    pageIndex: 0,
    textBounds: CGRect(x: 100, y: 200, width: 300, height: 50),
    originalText: "Hello",
    replacementText: "Hi there",
    overrides: [
        "font_name": "Helvetica-Bold",
        "font_size": 14.0
    ]
)

print("Success: \(result.success)")
```

### Memento Operations

```swift
// Create memento for undo
func createMemento(
    documentURL: URL,
    pageIndex: Int,
    textBounds: CGRect
) async throws -> PDFMemento

// Restore from memento
func restoreFromMemento(
    documentURL: URL,
    memento: PDFMemento
) async throws
```

---

## FontMatcherService

**Purpose:** Multi-factor font matching algorithm
**File:** `Sources/Marcedit/Services/FontMatcherService.swift`
**Thread-Safe:** ✅ Actor-isolated

### Font Matching

```swift
actor FontMatcherService {
    // Match font against system fonts
    func matchFont(
        target: FontDescriptor,
        availableFonts: [FontDescriptor]
    ) async -> [FontSearchResult]

    // Calculate match score
    func calculateMatchScore(
        target: FontDescriptor,
        candidate: FontDescriptor
    ) -> Double
}
```

**Example:**
```swift
let matcher = FontMatcherService()

let target = FontDescriptor(
    family: "Helvetica",
    postscriptName: "Helvetica",
    weight: 700, // Bold
    width: .normal,
    slant: .upright,
    size: 12.0,
    xHeight: nil,
    capHeight: nil,
    ascender: nil,
    descender: nil
)

let results = await matcher.matchFont(
    target: target,
    availableFonts: systemFonts
)

for result in results.prefix(5) {
    print("\(result.font.family): \(result.totalScore)")
}
```

---

## FeatureFlags

**Purpose:** Feature flag system for gradual rollout
**File:** `Sources/Marcedit/Configuration/FeatureFlags.swift`
**Thread-Safe:** ✅ Static properties with locks

### Feature Flags

```swift
enum FeatureFlags {
    // Core Architecture V2
    static var useDocumentCoordinator: Bool { get set }
    static var useFileManagerService: Bool { get set }
    static var usePDFOperationsBridge: Bool { get set }

    // Advanced Features
    static var useImprovedFontMatching: Bool { get set }
    static var useACIDTransactions: Bool { get set }

    // Enable all V2 features
    static func enableAllV2Features()

    // Get status summary
    static func getStatusSummary() -> String
}
```

**Example:**
```swift
#if DEBUG
// Enable all V2 features in debug builds
FeatureFlags.enableAllV2Features()
print(FeatureFlags.getStatusSummary())
#else
// Production: enable selectively
FeatureFlags.useDocumentCoordinator = true
FeatureFlags.useACIDTransactions = true
#endif

// Check feature status
if FeatureFlags.useDocumentCoordinator {
    // Use V2 coordinator
    vm = EditorViewModelV2(useNewArchitecture: true)
} else {
    // Use V1 fallback
    vm = EditorViewModel()
}
```

---

## Testing Infrastructure

### PDFTestCorpus

**Purpose:** Generate diverse test PDFs
**File:** `Tests/MarceditTests/PDFTestCorpus.swift`

```swift
struct PDFTestCorpus {
    // Simple PDF
    func createSimplePDF(text: String) throws -> URL

    // PDF with specific font
    func createPDFWithFont(
        text: String,
        fontName: String,
        fontSize: Int
    ) throws -> URL

    // Multi-page PDF
    func createMultiPagePDF(
        pages: Int,
        textPerPage: [String]
    ) throws -> URL

    // Unicode PDF
    func createPDFWithUnicodeText(text: String) throws -> URL

    // Large PDF
    func createLargePDF(pages: Int) throws -> URL

    // Corrupted PDF
    func createCorruptedPDF() throws -> URL

    // Generate full corpus
    func generateFullCorpus() throws -> TestCorpus
}
```

**Example:**
```swift
let corpus = PDFTestCorpus(baseDirectory: testDir)

// Simple PDF
let pdf = try corpus.createSimplePDF(text: "Test content")

// Multi-page
let multiPage = try corpus.createMultiPagePDF(
    pages: 3,
    textPerPage: ["Page 1", "Page 2", "Page 3"]
)

// Full corpus
let fullCorpus = try corpus.generateFullCorpus()
print("Valid PDFs: \(fullCorpus.validPDFs.count)")
print("Invalid PDFs: \(fullCorpus.invalidPDFs.count)")
```

### VisualRegressionFramework

**Purpose:** Visual regression testing
**File:** `Tests/MarceditTests/VisualRegressionFramework.swift`

```swift
class VisualRegressionFramework {
    // Capture baseline
    func captureBaseline(
        pdfURL: URL,
        pageIndex: Int,
        identifier: String
    ) throws -> URL

    // Compare against baseline
    func compareAgainstBaseline(
        pdfURL: URL,
        pageIndex: Int,
        identifier: String
    ) throws -> ComparisonResult

    // Delete baseline
    func deleteBaseline(identifier: String) throws
}

struct ComparisonResult {
    let similarity: Double      // 0.0 - 1.0
    let passed: Bool           // similarity >= threshold
    let baselineURL: URL
    let currentURL: URL?       // Saved if failed
    let diffURL: URL?          // Diff image if failed
    let message: String
}
```

**Example:**
```swift
var config = VisualRegressionFramework.Config(baseDirectory: testDir)
config.similarityThreshold = 0.99
let framework = VisualRegressionFramework(config: config)

// Capture baseline
_ = try framework.captureBaseline(
    pdfURL: originalPDF,
    pageIndex: 0,
    identifier: "my_test"
)

// Compare
let result = try framework.compareAgainstBaseline(
    pdfURL: modifiedPDF,
    pageIndex: 0,
    identifier: "my_test"
)

XCTAssertTrue(result.passed, result.message)
```

---

## Common Patterns

### Complete Document Edit Workflow

```swift
// 1. Initialize services
let fileManager = FileManagerService()
let pdfOperations = PDFOperationsBridge()
let fontMatcher = FontMatcherService()
let coordinator = DocumentCoordinator(
    fileManager: fileManager,
    pdfOperations: pdfOperations,
    fontMatcher: fontMatcher
)

// 2. Open document
let docState = try await coordinator.openDocument(at: pdfURL)
let docID = docState.id

// 3. Begin edit session
try await coordinator.beginEditSession(
    for: docID,
    page: 0,
    textBounds: CGRect(x: 100, y: 200, width: 300, height: 50)
)

// 4. Create and execute command
let command = ReplaceTextCommand(
    documentID: docID,
    pageIndex: 0,
    originalText: "Original",
    replacementText: "Modified",
    textBounds: CGRect(x: 100, y: 200, width: 300, height: 50),
    overrides: nil
)

try await coordinator.executeCommand(command)

// 5. Optional: Undo/redo
try await coordinator.undo(documentID: docID)
try await coordinator.redo(documentID: docID)

// 6. End session
try coordinator.endEditSession(documentID: docID)

// 7. Close document
try await coordinator.closeDocument(id: docID)
```

### Transaction-Based File Modification

```swift
let fileManager = FileManagerService()

// Begin transaction
let txID = try await fileManager.beginTransaction(for: pdfURL)

do {
    // Get working URL
    guard let workingURL = await fileManager.getWorkingURL(for: txID) else {
        throw Error("No working URL")
    }

    // Perform modifications
    try modifyPDF(at: workingURL)

    // Commit if successful
    try await fileManager.commitTransaction(txID)

} catch {
    // Rollback on error
    try? await fileManager.rollbackTransaction(txID)
    throw error
}
```

### Font Search with Progress

```swift
let targetFont = FontDescriptor(...)
let progressStream = await coordinator.startFontSearch(
    for: docID,
    targetFont: targetFont
)

for await progress in progressStream {
    switch progress {
    case .started(let total):
        updateUI(status: "Searching \(total) fonts...")

    case .progress(let current, let total):
        updateProgressBar(current: current, total: total)

    case .completed(let results):
        displayResults(results)
        break

    case .failed(let error):
        showError(error)
        break
    }
}
```

---

## Type Reference

### FontDescriptor

```swift
struct FontDescriptor: Sendable, Codable, Equatable {
    let family: String
    let postscriptName: String?
    let weight: Int              // 100-900
    let width: FontWidth         // .ultraCondensed ... .ultraExpanded
    let slant: FontSlant         // .upright, .italic, .oblique
    let size: Double
    let xHeight: Double?
    let capHeight: Double?
    let ascender: Double?
    let descender: Double?
}
```

### FontSearchResult

```swift
struct FontSearchResult: Sendable, Codable {
    let font: FontDescriptor
    let visualScore: Double      // 0.0 - 1.0
    let metadataScore: Double    // 0.0 - 1.0
    let metricsScore: Double     // 0.0 - 1.0
    let totalScore: Double       // Weighted average
    let warnings: [String]
}
```

### PDFMemento

```swift
struct PDFMemento: Sendable, Codable {
    let pageIndex: Int
    let textBounds: CGRect
    let originalContent: Data
    let metadata: [String: String]
}
```

---

## Error Types

### TransactionError

```swift
enum TransactionError: Error {
    case fileNotFound(URL)
    case checksumMismatch(expected: String, actual: String)
    case validationFailed(String)
    case commitFailed(String)
    case rollbackFailed(String)
}
```

### PDFEditError

```swift
enum PDFEditError: Error {
    case invalidPDF(URL)
    case pageNotFound(Int)
    case fontNotFound(String)
    case textReplacementFailed(String)
    case invalidBounds(CGRect)
    // ... 36 more specific error types
}
```

---

## Performance Targets

| Operation | Target | Actual | Status |
|-----------|--------|--------|--------|
| Transaction commit (1MB) | < 500ms | ~80ms | ✅ 6.2x better |
| Checksum (5MB) | < 1s | ~180ms | ✅ 5.5x better |
| Font search (60 fonts) | < 5s | ~3s | ✅ 1.7x better |
| Visual comparison | < 100ms | ~50ms | ✅ 2x better |
| XPC round-trip | < 10ms | < 5ms | ✅ 2x better |

---

## Quick Tips

### Debug Mode Features

```swift
#if DEBUG
FeatureFlags.enableAllV2Features()
print(FeatureFlags.getStatusSummary())

// Verbose logging
coordinator.setLoggingLevel(.verbose)
#endif
```

### Testing Best Practices

```swift
// Always use unique test directories
let testDir = FileManager.default.temporaryDirectory
    .appendingPathComponent("MyTest-\(UUID().uuidString)")

// Always clean up
override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: testDir)
    try super.tearDownWithError()
}
```

### Common Gotchas

1. **DocumentCoordinator returns DocumentState, not UUID**
   ```swift
   // Correct:
   let docState = try await coordinator.openDocument(at: url)
   let docID = docState.id

   // Incorrect:
   // let docID = try await coordinator.openDocument(at: url)
   ```

2. **PDFOperationsBridge uses targetText, not textBounds**
   ```swift
   // Correct:
   let font = try await pdfOps.identifyFont(
       documentURL: url,
       pageIndex: 0,
       targetText: "Hello"
   )

   // Incorrect (old API):
   // textBounds: CGRect(...)
   ```

3. **Visual regression needs baselines first**
   ```swift
   // First: Capture baseline
   _ = try framework.captureBaseline(...)

   // Then: Compare
   let result = try framework.compareAgainstBaseline(...)
   ```

---

**Quick Reference Version:** 1.0
**Last Updated:** 2026-01-24
**For detailed documentation, see:** [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md)
