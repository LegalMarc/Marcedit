
import SwiftUI
import AppKit
import OSLog

// MARK: - Helpers
struct AlertInfo: Identifiable {
    let id = UUID()
    let title: String
    let message: String
}

extension URL {
    func appendingString(_ string: String) -> URL {
        let path = self.path + string
        return URL(fileURLWithPath: path)
    }

    /// Returns true if the URL lives in any well-known temporary directory.
    /// FileManager.temporaryDirectory returns /var/folders/… on macOS; /tmp and
    /// /private/tmp are also in common use (e.g. from NSTemporaryDirectory() and
    /// hardcoded paths in tests).
    var isTemporaryFile: Bool {
        let p = self.path
        return p.hasPrefix(FileManager.default.temporaryDirectory.path)
            || p.hasPrefix("/tmp/")
            || p.hasPrefix("/private/tmp/")
    }
}

// MARK: - Notifications
extension Notification.Name {
    static let attemptToCloseApp = Notification.Name("attemptToCloseApp")
    static let prepareForPDFReload = Notification.Name("prepareForPDFReload")
    static let didReloadPDF = Notification.Name("didReloadPDF")
    static let fontSearchCompleted = Notification.Name("fontSearchCompleted")

    // BUG #65 FIX: Type-safe notification names to prevent typos
    static let zoomIn = Notification.Name("ZoomIn")
    static let zoomOut = Notification.Name("ZoomOut")
    static let zoomFit = Notification.Name("ZoomFit")
    static let pdfViewScaleChanged = Notification.Name("PDFViewScaleChanged")
    static let pdfViewVisiblePagesChanged = Notification.Name("PDFViewVisiblePagesChanged")
    static let previewErrorChanged = Notification.Name("PreviewErrorChanged")

    // Test automation notifications
    static let LoadTestPDF = Notification.Name("LoadTestPDF")
    static let TriggerEditDialog = Notification.Name("TriggerEditDialog")
    static let SetEditText = Notification.Name("SetEditText")
    static let TogglePreview = Notification.Name("TogglePreview")
    static let TestQueryState = Notification.Name("TestQueryState")

    // Menu command notifications (posted by Commands, received by views)
    static let menuOpenPDF = Notification.Name("menuOpenPDF")
    static let menuToggleHelp = Notification.Name("menuToggleHelp")
    static let menuVectorFlatten = Notification.Name("menuVectorFlatten")
    static let menuViewMetadata = Notification.Name("menuViewMetadata")
    static let menuScrubMetadata = Notification.Name("menuScrubMetadata")
    static let menuSecureErase = Notification.Name("menuSecureErase")
}

/// Erase a file with best-effort multi-pass overwrite before deletion.
///
/// **APFS / SSD limitation:** On APFS (default since macOS 10.13) and any SSD,
/// overwriting a file's bytes typically allocates new blocks rather than
/// rewriting the original physical cells.  This function performs a logical
/// deletion plus a best-effort overwrite, but cannot guarantee that the original
/// data blocks are physically zeroed.  For at-rest protection use FileVault.
func secureErase(at url: URL) async throws {
    guard FileManager.default.fileExists(atPath: url.path) else {
        throw NSError(domain: "SecureErase", code: 1, userInfo: [NSLocalizedDescriptionKey: "File does not exist"])
    }

    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    let size = (attributes[.size] as? Int64) ?? 0

    if size > 0 {
        let intSize = Int(size)

        // Use non-atomic writes (.init([])) so each pass targets the existing file
        // rather than a fresh temp file.  Atomic write (the default) creates a new
        // inode per pass, which on APFS allocates new blocks and doesn't help.
        let writeOptions: Data.WritingOptions = []

        // Pass 1: Overwrite with zeros
        let zeros = Data(count: intSize)
        try zeros.write(to: url, options: writeOptions)

        // Pass 2: Overwrite with ones (0xFF)
        let ones = Data(repeating: 0xFF, count: intSize)
        try ones.write(to: url, options: writeOptions)

        // Pass 3: Overwrite with cryptographically random bytes
        var randomBytes = [UInt8](repeating: 0, count: intSize)
        let status = SecRandomCopyBytes(kSecRandomDefault, intSize, &randomBytes)
        if status != errSecSuccess {
            // Degrade gracefully rather than aborting — but log so it's observable.
            let log = OSLog(subsystem: "com.marcedit.app", category: "SecureErase")
            os_log(.error, log: log, "SecRandomCopyBytes failed (status %d); pass 3 writes zeros", status)
        }
        let random = status == errSecSuccess ? Data(randomBytes) : Data(count: intSize)
        try random.write(to: url, options: writeOptions)
    }

    // Then delete
    try FileManager.default.removeItem(at: url)
}

/// Securely erase a directory and all its contents with 3-pass overwrite
func secureEraseDirectory(at url: URL) async throws {
    guard FileManager.default.fileExists(atPath: url.path) else { return }

    let rootValues = try url.resourceValues(forKeys: [.isSymbolicLinkKey])
    if rootValues.isSymbolicLink == true {
        throw NSError(domain: "SecureErase", code: 3, userInfo: [NSLocalizedDescriptionKey: "Refusing to erase through symbolic link"])
    }
    
    let contents = try FileManager.default.contentsOfDirectory(
        at: url,
        includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey]
    )
    for item in contents {
        let values = try item.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        if values.isSymbolicLink == true {
            try FileManager.default.removeItem(at: item)
            continue
        }

        var isDir: ObjCBool = false
        if FileManager.default.fileExists(atPath: item.path, isDirectory: &isDir) {
            if isDir.boolValue {
                try await secureEraseDirectory(at: item)
            } else {
                try await secureErase(at: item)
            }
        }
    }
    // Remove the now-empty directory
    try FileManager.default.removeItem(at: url)
}
