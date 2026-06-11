import Foundation
import os.log
import AppKit

/// Manages file-based logging for the application.
/// Logs are written to the Application Support directory (App Store safe).
class LogManager: ObservableObject {
    static let shared = LogManager()
    
    private let logger = Logger(subsystem: "com.marclaw.Marcedit", category: "LogManager")
    private let fileManager = FileManager.default
    
    @Published var isLoggingEnabled: Bool {
        didSet {
            UserDefaults.standard.set(isLoggingEnabled, forKey: "debugLoggingEnabled")
        }
    }
    
    var logFileURL: URL {
        guard let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            return fileManager.temporaryDirectory.appendingPathComponent("marcedit.log")
        }
        let appDir = appSupport.appendingPathComponent("Marcedit", isDirectory: true)
        
        // Ensure directory exists
        if !fileManager.fileExists(atPath: appDir.path) {
            try? fileManager.createDirectory(at: appDir, withIntermediateDirectories: true)
        }
        
        return appDir.appendingPathComponent("marcedit.log")
    }
    
    private init() {
        self.isLoggingEnabled = UserDefaults.standard.bool(forKey: "debugLoggingEnabled")
    }
    
    /// Log a message to the file (if enabled) and to the system console.
    func log(_ message: String, level: OSLogType = .info) {
        let safeMessage = sanitizeForLogging(message)
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let logLine = "[\(timestamp)] \(safeMessage)\n"
        
        // Always log to system console
        switch level {
        case .error:
            logger.error("\(safeMessage)")
        case .debug:
            logger.debug("\(safeMessage)")
        default:
            logger.info("\(safeMessage)")
        }
        
        // Only write to file if logging is enabled
        guard isLoggingEnabled else { return }
        
        do {
            if fileManager.fileExists(atPath: logFileURL.path) {
                let handle = try FileHandle(forWritingTo: logFileURL)
                defer { try? handle.close() }
                handle.seekToEndOfFile()
                if let data = logLine.data(using: .utf8) {
                    handle.write(data)
                }
            } else {
                try logLine.write(to: logFileURL, atomically: true, encoding: .utf8)
            }
        } catch {
            logger.error("Failed to write to log file: \(error.localizedDescription)")
        }
    }

    /// Redact high-risk document data before it reaches OSLog or app log files.
    static func sanitizeForLogging(_ message: String) -> String {
        var sanitized = message

        let quotedFieldPatterns = [
            #"(?i)(targetText|replacementText|target|replacement|original|newText|page text sample|text)\s*[:=]\s*'[^']*'"#,
            #"(?i)(targetText|replacementText|target|replacement|original|newText|page text sample|text)\s*[:=]\s*"[^"]*""#
        ]

        for pattern in quotedFieldPatterns {
            sanitized = replace(pattern, in: sanitized) { match in
                guard let separatorRange = match.range(of: ":", options: .backwards) != nil
                    ? match.range(of: ":", options: .backwards)
                    : match.range(of: "=", options: .backwards) else {
                    return "<redacted>"
                }
                let key = String(match[..<separatorRange.lowerBound])
                return "\(key)\(match[separatorRange]) <redacted>"
            }
        }

        sanitized = replace(#"(?i)Page text sample:\s*.*"#, in: sanitized) { _ in
            "Page text sample: <redacted>"
        }
        sanitized = replace(#"(?i)Target unicode:\s*.*"#, in: sanitized) { _ in
            "Target unicode: <redacted>"
        }
        sanitized = replace(#"file:///(?:Users|private|tmp|var|Library|System|Applications|Volumes)/[^ \n\t'")\]]+"#, in: sanitized) { _ in
            "<path>"
        }
        sanitized = replace(#"/(?:Users|private|tmp|var|Library|System|Applications|Volumes)/[^ \n\t'")\]]+"#, in: sanitized) { _ in
            "<path>"
        }

        return sanitized
    }

    private func sanitizeForLogging(_ message: String) -> String {
        Self.sanitizeForLogging(message)
    }

    private static func replace(
        _ pattern: String,
        in input: String,
        transform: (String) -> String
    ) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            return input
        }

        let nsRange = NSRange(input.startIndex..<input.endIndex, in: input)
        let matches = regex.matches(in: input, range: nsRange).reversed()
        var output = input

        for match in matches {
            guard let range = Range(match.range, in: output) else { continue }
            let replacement = transform(String(output[range]))
            output.replaceSubrange(range, with: replacement)
        }

        return output
    }
    
    /// Clear the log file.
    func clearLog() {
        do {
            try "".write(to: logFileURL, atomically: true, encoding: .utf8)
            logger.info("Log file cleared")
        } catch {
            logger.error("Failed to clear log: \(error.localizedDescription)")
        }
    }
    
    /// Open the log file in Console.app or default text editor.
    func openLog() {
        // Ensure the file exists before opening
        if !fileManager.fileExists(atPath: logFileURL.path) {
            let timestamp = ISO8601DateFormatter().string(from: Date())
            let header = """
            --- Marcedit Log ---
            Created: \(timestamp)
            App Bundle: \(Bundle.main.bundlePath)
            ---
            
            """
            try? header.write(to: logFileURL, atomically: true, encoding: .utf8)
        }
        NSWorkspace.shared.open(logFileURL)
    }
}
