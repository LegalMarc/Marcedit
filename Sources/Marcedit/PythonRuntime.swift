import Foundation
import PythonKit
import Darwin

private typealias PyGILState_STATE = UnsafeMutableRawPointer?

private func loadPythonSymbol<T>(_ name: String, as type: T.Type) -> T {
    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), name) else {
        fatalError("Missing CPython symbol: \(name)")
    }
    return unsafeBitCast(symbol, to: type)
}

private func Py_IsInitialized() -> Int32 {
    let fn: @convention(c) () -> Int32 = loadPythonSymbol("Py_IsInitialized", as: (@convention(c) () -> Int32).self)
    return fn()
}

private func Py_Initialize() {
    let fn: @convention(c) () -> Void = loadPythonSymbol("Py_Initialize", as: (@convention(c) () -> Void).self)
    fn()
}

private func PyGILState_Ensure() -> PyGILState_STATE {
    let fn: @convention(c) () -> PyGILState_STATE = loadPythonSymbol("PyGILState_Ensure", as: (@convention(c) () -> PyGILState_STATE).self)
    return fn()
}

private func PyGILState_Release(_ state: PyGILState_STATE) {
    let fn: @convention(c) (PyGILState_STATE) -> Void = loadPythonSymbol("PyGILState_Release", as: (@convention(c) (PyGILState_STATE) -> Void).self)
    fn(state)
}

struct PythonRuntimeConfig {
    let libPath: String
    let pyHome: String
    let pyPaths: [String]
}

enum PythonInitError: Error {
    case frameworkNotFound(attemptedPaths: [String])
    case importFailed(String)
}

extension PythonInitError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .frameworkNotFound(let paths):
            if paths.isEmpty {
                return "Python.framework could not be located in the application bundle."
            } else {
                return "Python.framework not found. Searched \(paths.count) configured locations"
            }
        case .importFailed(let message):
            return "Failed to initialize Python runtime: \(message)"
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .frameworkNotFound:
            return "Please reinstall the application or contact support if the problem persists."
        case .importFailed:
            return "This may indicate a corrupted installation. Try reinstalling the application."
        }
    }
}

final class PythonRuntime {
    static func initialize(logger: @escaping (String) -> Void) throws -> PythonRuntimeConfig {
        sanitizeProcessEnvironment(logger: logger)
        guard let cfg = locateFramework(logger: logger) else {
            throw PythonInitError.frameworkNotFound(attemptedPaths: [])
        }

        logger("PYTHONHOME configured")
        logger("PYTHONPATH configured with \(cfg.pyPaths.count) entries")

        setenv("PYTHONHOME", cfg.pyHome, 1)
        setenv("PYTHONPATH", cfg.pyPaths.joined(separator: ":"), 1)
        setenv("PYTHONNOUSERSITE", "1", 1)
        setenv("PYTHONDONTWRITEBYTECODE", "1", 1)

        PythonLibrary.useLibrary(at: cfg.libPath)

        do {
            let sys = try Python.attemptImport("sys")
            _ = sys.version
        } catch {
            throw PythonInitError.importFailed("Python import failed: \(error)")
        }

        return cfg
    }

    private static func sanitizeProcessEnvironment(logger: (String) -> Void) {
        let keys = [
            "PYTHONHOME",
            "PYTHONPATH",
            "PYTHONSTARTUP",
            "PYTHONEXECUTABLE",
            "PYTHONUSERBASE",
            "PYTHONWARNINGS",
            "PYTHONNOUSERSITE",
            "PYTHONINSPECT",
            "PYENV_VERSION",
            "PYENV_ROOT",
            "CONDA_PREFIX",
            "CONDA_DEFAULT_ENV",
            "VIRTUAL_ENV"
        ]
        for key in keys where getenv(key) != nil {
            unsetenv(key)
            logger("Unset \(key)")
        }
    }

    static func locateFramework(logger: ((String) -> Void)? = nil) -> PythonRuntimeConfig? {
        let bundleURL = Bundle.main.bundleURL
        let fileManager = FileManager.default
        let log = logger ?? { _ in } // Use provided logger or no-op

        var candidates: [URL] = []
        
        // For .app bundles: look in Contents/Resources/Marcedit_Marcedit.bundle
        if let resourceURL = Bundle.main.resourceURL {
            let bundleInResources = resourceURL.appendingPathComponent("Marcedit_Marcedit.bundle", isDirectory: true)
            candidates.append(bundleInResources.appendingPathComponent("Frameworks", isDirectory: true).appendingPathComponent("Python.framework", isDirectory: true))
        }
        
        // For standalone SwiftPM executables: look for bundle next to the executable
        let executableDir = bundleURL.deletingLastPathComponent()
        let swiftPMBundle = executableDir.appendingPathComponent("Marcedit_Marcedit.bundle", isDirectory: true)
        candidates.append(swiftPMBundle.appendingPathComponent("Frameworks", isDirectory: true).appendingPathComponent("Python.framework", isDirectory: true))
        
        // Also try Bundle.module for SwiftPM
        if let moduleBundle = Bundle(identifier: "Marcedit_Marcedit") {
            candidates.append(moduleBundle.bundleURL.appendingPathComponent("Frameworks", isDirectory: true).appendingPathComponent("Python.framework", isDirectory: true))
        }
        
        // Standard app bundle locations
        if let privateFrameworks = Bundle.main.privateFrameworksURL {
            candidates.append(privateFrameworks.appendingPathComponent("Python.framework", isDirectory: true))
        }
        candidates.append(
            bundleURL
                .appendingPathComponent("Contents", isDirectory: true)
                .appendingPathComponent("Frameworks", isDirectory: true)
                .appendingPathComponent("Python.framework", isDirectory: true)
        )
        candidates.append(
            bundleURL
                .appendingPathComponent("Frameworks", isDirectory: true)
                .appendingPathComponent("Python.framework", isDirectory: true)
        )
        if let resourceURL = Bundle.main.resourceURL {
            candidates.append(resourceURL.appendingPathComponent("Frameworks", isDirectory: true).appendingPathComponent("Python.framework", isDirectory: true))
        }

        log("Searching for Python.framework in \(candidates.count) candidate locations...")
        var frameworkURL: URL?
        var attemptedPaths: [String] = []
        
        for candidate in candidates {
            let pythonLib = candidate.appendingPathComponent("Python")
            attemptedPaths.append(pythonLib.path)
            
            var isDirectory: ObjCBool = false
            let parentExists = fileManager.fileExists(atPath: candidate.path, isDirectory: &isDirectory)
            
            if !parentExists {
                log("  ✗ framework candidate missing")
            } else if !isDirectory.boolValue {
                log("  ✗ framework candidate is not a directory")
            } else if !fileManager.fileExists(atPath: pythonLib.path) {
                log("  ✗ Python binary not found in framework candidate")
            } else {
                log("  ✓ found valid Python binary")
                frameworkURL = candidate
                break
            }
        }
        
        guard let fwRoot = frameworkURL else {
            log("❌ Python.framework not found in any candidate location")
            log("Attempted \(attemptedPaths.count) Python framework paths")
            return nil
        }

        let versionsDir = fwRoot.appendingPathComponent("Versions")
        let currentLink = versionsDir.appendingPathComponent("Current")
        var pythonVersionDir = currentLink
        if let resolved = try? FileManager.default.destinationOfSymbolicLink(atPath: currentLink.path) {
            pythonVersionDir = URL(fileURLWithPath: resolved, relativeTo: versionsDir)
            log("✓ Resolved Python version symlink")
        } else {
            log("⚠️ Failed to resolve 'Current' symlink, using fallback")
            if let firstVersion = try? fileManager.contentsOfDirectory(at: versionsDir, includingPropertiesForKeys: nil).first {
                pythonVersionDir = firstVersion
                log("  Using first Python version directory")
            } else {
                log("  ❌ No Python version directories found")
            }
        }

        let versionComponent = pythonVersionDir.lastPathComponent
        let stdlibPath = pythonVersionDir
            .appendingPathComponent("lib", isDirectory: true)
            .appendingPathComponent("python\(versionComponent)", isDirectory: true)
        let sitePackagesPath = stdlibPath.appendingPathComponent("site-packages", isDirectory: true)

        guard fileManager.fileExists(atPath: stdlibPath.path) else {
            log("❌ Standard library not found")
            return nil
        }
        log("Found standard library")

        var pyPaths: [String] = []

        var siteCandidates: [URL] = []
        
        // For .app bundles: look in Contents/Resources/Marcedit_Marcedit.bundle/python_site
        if let resourceURL = Bundle.main.resourceURL {
            let bundleInResources = resourceURL.appendingPathComponent("Marcedit_Marcedit.bundle", isDirectory: true)
            siteCandidates.append(bundleInResources.appendingPathComponent("python_site", isDirectory: true))
        }
        
        // For standalone SwiftPM: look in the resource bundle next to the executable
        let swiftPMSite = executableDir.appendingPathComponent("Marcedit_Marcedit.bundle", isDirectory: true).appendingPathComponent("python_site", isDirectory: true)
        siteCandidates.append(swiftPMSite)
        
        if let resourcePath = Bundle.main.resourcePath {
            siteCandidates.append(URL(fileURLWithPath: resourcePath).appendingPathComponent("python_site", isDirectory: true))
        }
        siteCandidates.append(
            bundleURL
                .appendingPathComponent("Contents", isDirectory: true)
                .appendingPathComponent("Resources", isDirectory: true)
                .appendingPathComponent("python_site", isDirectory: true)
        )
        siteCandidates.append(
            bundleURL
                .appendingPathComponent("Resources", isDirectory: true)
                .appendingPathComponent("python_site", isDirectory: true)
        )

        log("Searching for python_site in \(siteCandidates.count) candidate locations...")
        // NOTE: We only use the FIRST python_site found - this is intentional to avoid import ambiguity
        for siteCandidate in siteCandidates {
            if fileManager.fileExists(atPath: siteCandidate.path) {
                log("  ✓ Found python_site")
                pyPaths.append(siteCandidate.path)
                break
            } else {
                log("  ✗ python_site candidate not found")
            }
        }

        if fileManager.fileExists(atPath: sitePackagesPath.path) {
            pyPaths.append(sitePackagesPath.path)
            log("Added site-packages")
        }
        pyPaths.append(stdlibPath.path)
        
        // NOTE: Python import path order matters!
        // Priority (first to last):
        //   1. Bundled python_site (our custom packages)
        //   2. Framework site-packages (if exists)
        //   3. Framework stdlib (base Python modules)
        log("Final PYTHONPATH entry count: \(pyPaths.count)")

        return PythonRuntimeConfig(
            libPath: fwRoot.appendingPathComponent("Python").path,
            pyHome: pythonVersionDir.path,
            pyPaths: pyPaths
        )
    }
}

/// Protocol defining the interface for Python operations to allow mocking
protocol PythonRunnerProtocol {
    func validateEnvironment() -> (success: Bool, message: String, details: [String: Any]?)
    func listAvailableFonts() throws -> [[String: String]]
    func replaceTextInPDF(inputPath: String, outputPath: String, targetText: String, replacementText: String, pageNumber: Int, manualOverrides: [String: Any]?) throws -> (success: Bool, modified: Bool, message: String, appliedInfo: [String: Any]?, substitutionWarning: String?)
    func identifyFont(inputPath: String, pageNumber: Int, targetText: String) throws -> [String: Any]
    func expandToParagraph(inputPath: String, pageNumber: Int, spanText: String) throws -> [String: Any]
    func getBlockSpans(inputPath: String, pageNumber: Int, spanText: String) throws -> (success: Bool, blockBbox: [Double], spans: [[String: Any]], message: String)
    func replaceBlockWithSpans(inputPath: String, outputPath: String, pageNumber: Int, blockBbox: [Double], spans: [[String: Any]], overrides: [String: Any]?) throws -> (success: Bool, modified: Bool, message: String, debugLog: [String])
    func findFontInteractive(inputPath: String, pageIndex: Int, text: String, exhaustive: Bool, callback: @escaping (String, Double) -> Void) throws -> [String: Any]?
    func flattenDocument(inputPath: String, outputPath: String) throws -> (success: Bool, message: String, logs: [String])
    func scrubMetadata(inputPath: String, outputPath: String, dataDir: String?) -> (success: Bool, message: String, log: [String], reportHTML: String?, extractedFiles: [[String: Any]]?, warnings: [String])
    func extractMetadata(inputPath: String) -> (success: Bool, reportHTML: String?, error: String?)
}

final class PythonKitRunner: PythonRunnerProtocol {
    let worker: PythonWorkerThread
    private let logger: (String) -> Void
    let config: PythonRuntimeConfig

    init(logger: @escaping (String) -> Void) throws {
        self.logger = logger
        self.worker = PythonWorkerThread()
        worker.start()
        worker.waitUntilReady()
        self.config = try worker.perform {
            try PythonRuntime.initialize(logger: logger)
        }
        logger("Python runtime ready")
    }

    deinit {
        worker.stop()
    }
    
    /// Validate that Python environment is properly configured by testing imports.
    /// Returns (success, message, details) - call this after init to catch early failures.
    func validateEnvironment() -> (success: Bool, message: String, details: [String: Any]?) {
        do {
            // Collect log messages and detailed error info inside GIL, emit them after
            let result: (success: Bool, message: String, logs: [String], errorDetails: [String: Any]?) = try worker.perform { [self] in
                try self.withGIL {
                    var logs: [String] = []
                    
                    // Test basic Python
                    let sys = try Python.attemptImport("sys")
                    let version = String(sys.version) ?? "unknown"
                    logs.append("Python version: \(version)")
                    
                    // Capture sys.path for diagnostics
                    let sysPath = sys.path
                    var pathList: [String] = []
                    if let count = Int(Python.len(sysPath)) {
                        for i in 0..<count {
                            if let p = String(sysPath[i]) {
                                pathList.append(p)
                            }
                        }
                    }
                    
                    // Test editor_pkg
                    do {
                        _ = try Python.attemptImport("editor_pkg.core")
                        logs.append("✓ editor_pkg.core imported successfully")
                    } catch {
                        var errorDetails: [String: Any] = [
                            "module": "editor_pkg.core",
                            "error": String(describing: error),
                            "sys.path": pathList
                        ]
                        
                        // Try to capture Python traceback
                        let traceback = Python.import("traceback")
                        if let tbStr = String(traceback.format_exc()) {
                            errorDetails["traceback"] = tbStr
                            logs.append("Traceback: \(tbStr)")
                        }
                        
                        return (false, "Failed to import editor_pkg.core: \(error)", logs, errorDetails)
                    }
                    
                    // Test PyMuPDF (fitz) - primary PDF library
                    do {
                        let fitz = try Python.attemptImport("fitz")
                        let fitzVersion = String(fitz.version[0]) ?? "unknown"
                        logs.append("✓ PyMuPDF \(fitzVersion) imported successfully")
                    } catch {
                        var errorDetails: [String: Any] = [
                            "module": "fitz",
                            "error": String(describing: error),
                            "sys.path": pathList
                        ]
                        
                        // Try to capture Python traceback
                        let traceback = Python.import("traceback")
                        if let tbStr = String(traceback.format_exc()) {
                            errorDetails["traceback"] = tbStr
                            logs.append("Traceback: \(tbStr)")
                        }
                        
                        return (false, "Failed to import fitz (PyMuPDF): \(error)", logs, errorDetails)
                    }
                    
                    return (true, "All Python modules validated", logs, nil)
                }
            }
            
            // Emit logs outside GIL
            for log in result.logs {
                logger(LogManager.sanitizeForLogging(log))
            }
            
            return (success: result.success, message: result.message, details: result.errorDetails)
        } catch {
            return (false, "Validation failed: \(error)", ["error": String(describing: error)])
        }
    }

    // REMOVED: callHello was a test stub that referenced non-existent example_pkg.core
    
    func listAvailableFonts() throws -> [[String: String]] {
        let result: [[String: String]] = try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                if Bool(Python.hasattr(editorModule, "list_available_fonts")) == true {
                    let function = editorModule.list_available_fonts
                    let fonts = try function.throwing.dynamicallyCall(withArguments: [])
                    // Convert Python list of dicts to Swift [[String:String]] safely (avoiding iterator)
                    var swiftFonts: [[String: String]] = []
                    if let count = Int(Python.len(fonts)) {
                        for i in 0..<count {
                            let dict = fonts[i]
                            var swiftDict: [String: String] = [:]
                            
                            // Explicitly access known keys (using .checking for safety)
                            let knownKeys = ["name", "id", "family", "style", "path", "type"]
                            for key in knownKeys {
                                if let value = dict.checking[key], value != Python.None, let v = String(value) {
                                    swiftDict[key] = v
                                }
                            }
                            swiftFonts.append(swiftDict)
                        }
                    }
                    return swiftFonts
                }
                return []
            }
        }
        return result
    }

    /// Replace text in a PDF page using pikepdf
    func replaceTextInPDF(
        inputPath: String,
        outputPath: String,
        targetText: String,
        replacementText: String,
        pageNumber: Int,
        manualOverrides: [String: Any]? = nil
    ) throws -> (success: Bool, modified: Bool, message: String, appliedInfo: [String: Any]?, substitutionWarning: String?) {
        let result = try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                
                // Convert manualOverrides to Python dict if present
                // Supported types: Int, Double, String, Bool
                var pyOverrides: PythonObject = Python.None
                if let overrides = manualOverrides {
                    let dict = Python.dict()
                    for (k, v) in overrides {
                        if let i = v as? Int { dict[k] = PythonObject(i) }
                        else if let d = v as? Double { dict[k] = PythonObject(d) }
                        else if let s = v as? String { dict[k] = PythonObject(s) }
                        else if let b = v as? Bool { dict[k] = PythonObject(b) }
                        else {
                            // Log warning for unsupported types
                            let typeName = type(of: v)
                            return (success: false, modified: false, message: "Unsupported type in manual overrides: \(k) = \(typeName). Supported types: Int, Double, String, Bool", logs: [], appliedInfo: nil as [String: Any]?, substitutionWarning: nil as String?)
                        }
                    }
                    pyOverrides = dict
                }
                
                let function = editorModule.replace_text_in_pdf
                let result = try function.throwing.dynamicallyCall(withArguments: [
                    inputPath, outputPath, targetText, replacementText, pageNumber, pyOverrides
                ])
                
                // Use checking subscripts for safety (with explicit optional handling)
                // Note: Bool(PythonObject) can fail, so try Python.bool() as fallback
                func extractBool(_ obj: PythonObject?) -> Bool {
                    guard let o = obj, o != Python.None else { return false }
                    // Try direct Bool conversion first
                    if let b = Bool(o) { return b }
                    // Fallback: use Python's bool()
                    if let b = Bool(Python.bool(o)) { return b }
                    return false
                }
                
                let success = extractBool(result.checking["success"])
                let modified = extractBool(result.checking["modified"])
                let message = (result.checking["message"]).flatMap { String($0) } ?? "Unknown error"
                
                // Extract debug logs safely (using index loop to avoid iterator crash)
                var logs: [String] = []
                if let debugLog = result.checking["debug_log"], debugLog != Python.None {
                    if let count = Int(Python.len(debugLog)) {
                        for i in 0..<count {
                            if let s = String(debugLog[i]) {
                                logs.append(LogManager.sanitizeForLogging(s))
                            }
                        }
                    }
                }
                
                // Extract applied info
                var appliedInfo: [String: Any]? = nil
                if let info = result.checking["applied_info"], info != Python.None {
                     var dict: [String: Any] = [:]
                     let knownKeys = ["final_font", "final_size", "font_source"]
                     for key in knownKeys {
                             if let v = info.checking[key], v != Python.None {
                             if let d = Double(v) { dict[key] = d }
                             else if let s = String(v) { dict[key] = s }
                         }
                     }
                     appliedInfo = dict
                }
                
                // Extract substitution warning
                var substitutionWarning: String? = nil
                if let warning = result.checking["substitution_warning"], warning != Python.None {
                    substitutionWarning = String(warning)
                }
                
                return (success: success, modified: modified, message: message, logs: logs, appliedInfo: appliedInfo, substitutionWarning: substitutionWarning)
            }
        }
        
        if !result.logs.isEmpty {
            logger("Core: debugLogEntries=\(result.logs.count)")
        }
        
        return (success: result.success, modified: result.modified, message: result.message, appliedInfo: result.appliedInfo, substitutionWarning: result.substitutionWarning)
    }



    /// Identify the font of a specific text on a page
    func identifyFont(inputPath: String, pageNumber: Int, targetText: String) throws -> [String: Any] {
        return try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                let function = editorModule.identify_font
                let result = try function.throwing.dynamicallyCall(withArguments: [inputPath, pageNumber, targetText])
                
                var info: [String: Any] = [:]
                if result != Python.None {
                    // Extract all keys with proper type handling
                    let numericKeys = ["fontsize", "flags", "ascend", "descend"]
                    let stringKeys = ["fontname", "message"]
                    let boolKeys = ["success"]
                    
                    // Handle numeric keys
                    for key in numericKeys {
                        if let val = result.checking[key], val != Python.None, let d = Double(val) {
                            info[key] = d
                        }
                    }
                    
                    // Handle string keys
                    for key in stringKeys {
                        if let val = result.checking[key], val != Python.None, let s = String(val) {
                            info[key] = s
                        }
                    }
                    
                    // Handle boolean keys
                    for key in boolKeys {
                        if let val = result.checking[key], val != Python.None, let b = Bool(val) {
                            info[key] = b
                        }
                    }
                }
                return info
            }
        }
    }

    /// Expand a text span to include adjacent spans in the same paragraph/block
    func expandToParagraph(inputPath: String, pageNumber: Int, spanText: String) throws -> [String: Any] {
        return try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                
                // Check if function exists
                if Bool(Python.hasattr(editorModule, "expand_to_paragraph")) != true {
                    return ["expanded_text": spanText, "message": "expand_to_paragraph not implemented"]
                }
                
                let function = editorModule.expand_to_paragraph
                let result = try function.throwing.dynamicallyCall(withArguments: [inputPath, pageNumber, spanText])
                
                var info: [String: Any] = [:]
                if result != Python.None {
                    if let expandedText = result.checking["expanded_text"], expandedText != Python.None {
                        info["expanded_text"] = String(expandedText) ?? spanText
                    }
                    if let message = result.checking["message"], message != Python.None {
                        info["message"] = String(message) ?? ""
                    }
                }
                return info
            }
        }
    }

    /// Get all spans from a text block with full styling information
    func getBlockSpans(inputPath: String, pageNumber: Int, spanText: String) throws -> (success: Bool, blockBbox: [Double], spans: [[String: Any]], message: String) {
        let result = try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                
                if Bool(Python.hasattr(editorModule, "get_block_spans")) != true {
                    return (success: false, blockBbox: [Double](), spans: [[String: Any]](), message: "get_block_spans not implemented")
                }
                
                let function = editorModule.get_block_spans
                let result = try function.throwing.dynamicallyCall(withArguments: [inputPath, pageNumber, spanText])
                
                // Extract success
                let success = Bool(result.checking["success"] ?? Python.False) ?? false
                
                // Extract block_bbox
                var blockBbox: [Double] = []
                if let bbox = result.checking["block_bbox"], bbox != Python.None {
                    if let count = Int(Python.len(bbox)) {
                        for i in 0..<count {
                            if let val = Double(bbox[i]) {
                                blockBbox.append(val)
                            }
                        }
                    }
                }
                
                // Extract spans array
                var spans: [[String: Any]] = []
                if let spansArr = result.checking["spans"], spansArr != Python.None {
                    if let count = Int(Python.len(spansArr)) {
                        for i in 0..<count {
                            let span = spansArr[i]
                            var spanDict: [String: Any] = [:]
                            
                            // Extract string fields
                            if let text = span.checking["text"], text != Python.None {
                                spanDict["text"] = String(text) ?? ""
                            }
                            if let font = span.checking["font"], font != Python.None {
                                spanDict["font"] = String(font) ?? ""
                            }
                            
                            // Extract numeric fields
                            if let size = span.checking["size"], size != Python.None {
                                spanDict["size"] = Double(size) ?? 12.0
                            }
                            if let flags = span.checking["flags"], flags != Python.None {
                                spanDict["flags"] = Int(flags) ?? 0
                            }
                            if let lineIndex = span.checking["line_index"], lineIndex != Python.None {
                                spanDict["line_index"] = Int(lineIndex) ?? 0
                            }
                            
                            // Extract boolean fields
                            if let isBold = span.checking["is_bold"], isBold != Python.None {
                                spanDict["is_bold"] = Bool(isBold) ?? false
                            }
                            if let isItalic = span.checking["is_italic"], isItalic != Python.None {
                                spanDict["is_italic"] = Bool(isItalic) ?? false
                            }
                            
                            // Extract color array
                            if let color = span.checking["color"], color != Python.None {
                                var colorArr: [Double] = []
                                if let colorCount = Int(Python.len(color)) {
                                    for j in 0..<colorCount {
                                        if let c = Double(color[j]) {
                                            colorArr.append(c)
                                        }
                                    }
                                }
                                spanDict["color"] = colorArr
                            }
                            
                            // Extract bbox array
                            if let bbox = span.checking["bbox"], bbox != Python.None {
                                var bboxArr: [Double] = []
                                if let bboxCount = Int(Python.len(bbox)) {
                                    for j in 0..<bboxCount {
                                        if let b = Double(bbox[j]) {
                                            bboxArr.append(b)
                                        }
                                    }
                                }
                                spanDict["bbox"] = bboxArr
                            }
                            
                            spans.append(spanDict)
                        }
                    }
                }
                
                // Extract message
                let message = String(result.checking["message"] ?? Python.None) ?? ""
                
                return (success: success, blockBbox: blockBbox, spans: spans, message: message)
            }
        }
        return result
    }

    /// Replace a text block with styled spans
    func replaceBlockWithSpans(
        inputPath: String,
        outputPath: String,
        pageNumber: Int,
        blockBbox: [Double],
        spans: [[String: Any]],
        overrides: [String: Any]? = nil
    ) throws -> (success: Bool, modified: Bool, message: String, debugLog: [String]) {
        let result = try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                
                if Bool(Python.hasattr(editorModule, "replace_block_with_spans")) != true {
                    return (success: false, modified: false, message: "replace_block_with_spans not implemented", debugLog: [String]())
                }
                
                // Convert Swift arrays to Python
                let pyBlockBbox = Python.list(blockBbox)
                
                // Convert spans array of dicts to Python
                let pySpans = Python.list()
                for span in spans {
                    let pySpan = Python.dict()
                    for (key, value) in span {
                        if let strVal = value as? String {
                            pySpan[key] = PythonObject(strVal)
                        } else if let doubleVal = value as? Double {
                            pySpan[key] = PythonObject(doubleVal)
                        } else if let intVal = value as? Int {
                            pySpan[key] = PythonObject(intVal)
                        } else if let boolVal = value as? Bool {
                            pySpan[key] = PythonObject(boolVal)
                        } else if let arrVal = value as? [Double] {
                            pySpan[key] = Python.list(arrVal)
                        }
                    }
                    pySpans.append(pySpan)
                }
                
                // Convert overrides
                let pyOverrides = Python.dict()
                if let ov = overrides {
                    for (k, v) in ov {
                        if let s = v as? String { pyOverrides[k] = PythonObject(s) }
                        else if let d = v as? Double { pyOverrides[k] = PythonObject(d) }
                        else if let i = v as? Int { pyOverrides[k] = PythonObject(i) }
                        else if let b = v as? Bool { pyOverrides[k] = PythonObject(b) }
                    }
                }

                let function = editorModule.replace_block_with_spans
                let result = try function.throwing.dynamicallyCall(withArguments: [
                    inputPath, outputPath, pageNumber, pyBlockBbox, pySpans, pyOverrides
                ])
                
                let success = Bool(result.checking["success"] ?? Python.False) ?? false
                let modified = Bool(result.checking["modified"] ?? Python.False) ?? false
                let message = String(result.checking["message"] ?? Python.None) ?? ""
                
                var debugLog: [String] = []
                if let logs = result.checking["debug_log"], logs != Python.None {
                    if let count = Int(Python.len(logs)) {
                        for i in 0..<count {
                            if let s = String(logs[i]) {
                                debugLog.append(LogManager.sanitizeForLogging(s))
                            }
                        }
                    }
                }
                
                return (success: success, modified: modified, message: message, debugLog: debugLog)
            }
        }
        return result
    }

    /// Find best font match with interactive progress feedback
    /// - Parameters:
    ///   - inputPath: Path to the PDF document
    ///   - pageIndex: Page index in current document
    ///   - text: Target text to find font for
    ///   - exhaustive: Whether to search all system fonts
    ///   - callback: Progress callback (message, progress 0-1). WARNING: Called from PythonWorkerThread, NOT main thread.
    ///               Callers must dispatch to MainActor for UI updates.
    /// - Returns: Result dictionary with 'success', 'best_match', 'candidates' keys
    func findFontInteractive(
        inputPath: String,
        pageIndex: Int,
        text: String,
        exhaustive: Bool,
        callback: @escaping (String, Double) -> Void
    ) throws -> [String: Any]? {
        let result = try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                
                // Call generator function with document path
                let function = editorModule.find_font_interactive
                let generator = try function.throwing.dynamicallyCall(withArguments: [inputPath, pageIndex, text, exhaustive])
                
                // Iterate over generator
                // Generator yields dicts: {'type': '...', ...}
                var finalResult: [String: Any]? = ["success": false, "message": "Generator did not complete"]
                
                // Iterate manually using Python.next to avoid PythonObject Sequence crash
                // Python.builtins["next"] returns PythonObject, not Optional
                let nextFunc = Python.builtins["next"]
                let stopIteration = Python.None // Sentinel
                
                // Max iterations to prevent infinite loop (10000 fonts is more than enough)
                let maxIterations = 10000
                var iterationCount = 0
                
                while true {
                    iterationCount += 1
                    if iterationCount > maxIterations {
                        return ["success": false, "message": "Generator exceeded maximum iterations"] as [String: Any]?
                    }
                    // event = next(generator, None)
                    // Use throwing call to catch potential Python exceptions
                    let event: PythonObject
                    do {
                        event = try nextFunc.throwing.dynamicallyCall(withArguments: [generator, stopIteration])
                    } catch {
                        return ["success": false, "message": "Python generator iteration failed: \(error)"] as [String: Any]?
                    }
                    
                    if event == stopIteration {
                        break
                    }
                    
                    if let dict = Dictionary<String, PythonObject>(event),
                       let typeObj = dict["type"],
                       let type = String(typeObj) {
                        
                        if type == "progress" {
                            if let msgObj = dict["message"], let msg = String(msgObj),
                               let progObj = dict["progress"], let prog = Double(progObj) {
                                callback(msg, prog)
                            }
                        } else if type == "complete" {
                            // Construct final result
                            var res: [String: Any] = ["success": true]
                            
                            // Best Match
                            if let best = dict["best_match"], best != Python.None {
                                 if let bDict = Dictionary<String, PythonObject>(best) {
                                    if let pathObj = bDict["path"], let nameObj = bDict["name"], let scoreObj = bDict["score"] {
                                        res["best_match"] = [
                                            "path": String(pathObj) ?? "",
                                            "name": String(nameObj) ?? "",
                                            "score": Double(scoreObj) ?? 0.0
                                        ]
                                    }
                                 }
                            }
                            
                            // Candidates
                            if let candidates = dict["candidates"], candidates != Python.None {
                                if let cList = Array<PythonObject>(candidates) {
                                    var swiftCandidates: [[String: Any]] = []
                                    for c in cList {
                                        if let cDict = Dictionary<String, PythonObject>(c),
                                           let pathObj = cDict["path"], let nameObj = cDict["name"], let scoreObj = cDict["score"] {
                                            swiftCandidates.append([
                                                "path": String(pathObj) ?? "",
                                                "name": String(nameObj) ?? "",
                                                "score": Double(scoreObj) ?? 0.0
                                            ])
                                        }
                                    }
                                    // Limit to top 5
                                    res["candidates"] = Array(swiftCandidates.prefix(5))
                                }
                            }
                            
                            // Source (for deterministic match labeling)
                            if let sourceObj = dict["source"], sourceObj != Python.None,
                               let source = String(sourceObj) {
                                res["source"] = source
                            }
                            
                            finalResult = res
                            break // Exit loop after receiving complete event
                        } else if type == "error" {
                            if let msgObj = dict["message"] {
                                let msg = String(msgObj) ?? "Unknown error"
                                finalResult = ["success": false, "message": msg]
                            } else {
                                finalResult = ["success": false, "message": "Unknown error"]
                            }
                            break // Exit loop after receiving error event
                        }
                    } else {
                        // Log malformed event for debugging
                        #if DEBUG
                        print("[FontSearch] Malformed generator event: \(event)")
                        #endif
                    }
                }
                
                return finalResult
            }
        }
        return result
    }

    /// Flatten document to vector outlines
    func flattenDocument(inputPath: String, outputPath: String) throws -> (success: Bool, message: String, logs: [String]) {
        return try worker.perform { [self] in
            try self.withGIL {
                let editorModule = try Python.attemptImport("editor_pkg.core")
                let function = editorModule.flatten_document_to_outlines
                
                let result = try function.throwing.dynamicallyCall(withArguments: [inputPath, outputPath])
                
                
                let success = result.checking["success"].flatMap { Bool($0) } ?? false
                let logObj = result.checking["log"] ?? Python.None
                let messageObj = result.checking["error"] ?? Python.None
                
                var logs: [String] = []
                if logObj != Python.None, let count = Int(Python.len(logObj)) {
                    for i in 0..<count {
                        if let s = String(logObj[i]) { logs.append(s) }
                    }
                }
                
                let message = String(messageObj) ?? (success ? "Success" : "Unknown error")
                
                return (success, message, logs)
            }
        }
    }

    /// Enhanced metadata scrub with report generation
    /// - Parameters:
    ///   - inputPath: Source PDF path
    ///   - outputPath: Destination for scrubbed PDF
    ///   - dataDir: Optional directory to save extracted attachments and long values
    /// - Returns: Tuple with success status, message, logs, and optional report HTML path
    func scrubMetadata(
        inputPath: String,
        outputPath: String,
        dataDir: String? = nil
    ) -> (success: Bool, message: String, log: [String], reportHTML: String?, extractedFiles: [[String: Any]]?, warnings: [String]) {
        do {
            return try worker.perform { [self] in
                try self.withGIL {
                    let core = try Python.attemptImport("editor_pkg.core")

                    // Call with data_dir parameter if provided
                    let result: PythonObject
                    if let dir = dataDir {
                        result = core.scrub_all_metadata(inputPath, outputPath, dir)
                    } else {
                        result = core.scrub_all_metadata(inputPath, outputPath, Python.None)
                    }
                    
                    let success = result.checking["success"].flatMap { Bool($0) } ?? false
                    let messageObj = result.checking["error"] ?? Python.None
                    let message = String(messageObj) ?? (success ? "Scrub complete" : "Unknown error")
                    
                    // Extract logs
                    var logs: [String] = []
                    let logObj = result.checking["log"] ?? Python.None
                    if logObj != Python.None, let count = Int(Python.len(logObj)) {
                        for i in 0..<count {
                            if let s = String(logObj[i]) { logs.append(s) }
                        }
                    }
                    
                    // Extract report HTML
                    var reportHTML: String? = nil
                    if let htmlObj = result.checking["report_html"], htmlObj != Python.None {
                        reportHTML = String(htmlObj)
                    }
                    
                    // Extract extracted files list
                    var extractedFiles: [[String: Any]]? = nil
                    if let filesObj = result.checking["extracted_files"], filesObj != Python.None {
                        if let count = Int(Python.len(filesObj)), count > 0 {
                            var files: [[String: Any]] = []
                            for i in 0..<count {
                                let fileObj = filesObj[i]
                                var fileDict: [String: Any] = [:]
                                if let name = fileObj.checking["name"].flatMap({ String($0) }) {
                                    fileDict["name"] = name
                                }
                                if let path = fileObj.checking["path"].flatMap({ String($0) }) {
                                    fileDict["path"] = path
                                }
                                if let size = fileObj.checking["size"].flatMap({ Int($0) }) {
                                    fileDict["size"] = size
                                }
                                files.append(fileDict)
                            }
                            extractedFiles = files
                        }
                    }
                    
                    // Extract warnings
                    var warnings: [String] = []
                    if let warnObj = result.checking["warnings"], warnObj != Python.None,
                       let count = Int(Python.len(warnObj)) {
                        for i in 0..<count {
                            if let s = String(warnObj[i]) { warnings.append(s) }
                        }
                    }

                    return (success, message, logs, reportHTML, extractedFiles, warnings)
                }
            }
        } catch {
            return (false, "Scrub failed: \(error.localizedDescription)", [], nil, nil, [])
        }
    }
    
    /// Extract metadata from PDF without modifying it (view-only mode)
    /// - Parameter inputPath: Path to PDF file
    /// - Returns: Tuple with success status, report HTML, and error message if any
    func extractMetadata(inputPath: String) -> (success: Bool, reportHTML: String?, error: String?) {
        do {
            return try worker.perform { [self] in
                try self.withGIL {
                    let core = try Python.attemptImport("editor_pkg.core")

                    // Extract metadata without scrubbing
                    let result = core.extract_all_metadata(inputPath)
                    
                    let success = result.checking["success"].flatMap { Bool($0) } ?? false
                    
                    if !success {
                        let error = result.checking["error"].flatMap { String($0) } ?? "Unknown error"
                        return (false, nil, error)
                    }
                    
                    // Generate report HTML for display (view-only - no "after" data)
                    let sourceFilename = URL(fileURLWithPath: inputPath).lastPathComponent
                    
                    // Call generate_scrub_report with the same data for before/after
                    // to show current state (no changes)
                    let emptyList = Python.list()
                    let reportResult = core.generate_scrub_report(
                        result,  // before
                        result,  // after (same = no changes shown)
                        emptyList,  // no extracted files
                        sourceFilename,
                        "metadata"
                    )
                    
                    // generate_scrub_report returns (html, long_values) tuple
                    var reportHTML: String? = nil
                    let htmlObj = reportResult[0]
                    if htmlObj != Python.None {
                        reportHTML = String(htmlObj)
                    }
                    
                    return (true, reportHTML, nil)
                }
            }
        } catch {
            return (false, nil, "Extract failed: \(error.localizedDescription)")
        }
    }

    // Thread-safe Python initialization using dispatch_once pattern
    private static let initOnce: () = {
        if Py_IsInitialized() == 0 {
            Py_Initialize()
        }
    }()
    
    func withGIL<T>(_ operation: () throws -> T) rethrows -> T {
        // Ensure Python is initialized exactly once, thread-safely
        _ = PythonKitRunner.initOnce
        
        let state = PyGILState_Ensure()
        defer { PyGILState_Release(state) }
        return try operation()
    }
}

// Make PythonWorkerThread internal so it can be accessed by extensions
final class PythonWorkerThread: Thread {
    private let condition = NSCondition()
    private var tasks: [() -> Void] = []
    private var running = true
    private let readySemaphore = DispatchSemaphore(value: 0)

    // Thread-local key to detect re-entrant calls from within the worker.
    private static let isWorkerKey = "PythonWorkerThread.isWorkerThread"

    private var isCalledFromWorkerThread: Bool {
        Thread.current.threadDictionary[Self.isWorkerKey] as? Bool == true
    }

    override init() {
        super.init()
        name = "PythonWorkerThread"
    }

    override func main() {
        // Mark this thread so perform() can detect re-entrant calls.
        Thread.current.threadDictionary[Self.isWorkerKey] = true
        readySemaphore.signal()
        while true {
            var task: (() -> Void)?
            condition.lock()
            while tasks.isEmpty && running {
                condition.wait()
            }
            if !running && tasks.isEmpty {
                condition.unlock()
                return
            }
            task = tasks.isEmpty ? nil : tasks.removeFirst()
            condition.unlock()
            
            // Drain autorelease pool to prevent memory accumulation in long-running thread
            if let task = task {
                autoreleasepool {
                    task()
                }
            }
        }
    }

    func waitUntilReady() {
        readySemaphore.wait()
    }

    func stop() {
        condition.lock()
        running = false
        condition.signal()
        condition.unlock()
    }

    private func enqueue(_ work: @escaping () -> Void) {
        condition.lock()
        tasks.append(work)
        condition.signal()
        condition.unlock()
    }

    func perform<T>(_ work: @escaping () throws -> T) throws -> T {
        // If the caller is already on the worker thread, run inline to avoid
        // self-deadlock (enqueuing behind the currently-running task that is
        // itself blocked on the semaphore below).
        if isCalledFromWorkerThread {
            return try work()
        }
        let semaphore = DispatchSemaphore(value: 0)
        var result: Result<T, Error>?
        enqueue {
            do {
                result = .success(try work())
            } catch {
                result = .failure(error)
            }
            semaphore.signal()
        }
        semaphore.wait()
        guard let result = result else {
            throw NSError(domain: "PythonWorkerThread", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "Worker thread failed to execute task"])
        }
        return try result.get()
    }
}
