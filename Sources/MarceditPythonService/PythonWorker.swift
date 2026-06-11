//
//  PythonWorker.swift
//  MarceditPythonService
//
//  Created: 2026-01-23
//  Purpose: Handles Python execution in XPC service process
//

import Foundation
import CoreGraphics
import PythonKit

/// Worker class that executes Python operations in the XPC service
class PythonWorker: NSObject, PythonServiceProtocol {

    // MARK: - Properties

    private var pythonInitialized = false
    private var pythonSys: PythonObject?
    private var editorCore: PythonObject?

    private let workQueue = DispatchQueue(
        label: "com.marcedit.python-service.work",
        qos: .userInitiated
    )

    // MARK: - Initialization

    override init() {
        super.init()
        initializePython()
    }

    // MARK: - Python Initialization

    private func initializePython() {
        workQueue.sync { [weak self] in
            guard let self = self else { return }

            // Set Python path
            guard let pythonLibPath = self.findPythonLibrary() else {
                print("[PythonWorker] ERROR: Could not find Python library")
                return
            }

            PythonLibrary.useLibrary(at: pythonLibPath)

            // Import sys
            self.pythonSys = Python.import("sys")

            // Add python_site to path
            if let pythonSitePath = self.getPythonSitePath() {
                self.pythonSys?.path.insert(0, pythonSitePath)
                print("[PythonWorker] Added python_site to sys.path: \(pythonSitePath)")
            }

            // Import editor_pkg.core_xpc (XPC-compatible wrappers)
            self.editorCore = Python.import("editor_pkg.core_xpc")

            self.pythonInitialized = true
            print("[PythonWorker] Python initialized successfully with XPC wrappers")
        }
    }

    private func findPythonLibrary() -> String? {
        // Only use the bundled Python framework — never fall back to a system or
        // Homebrew install, which would be a dylib-hijack surface and version-drift risk.
        let bundle = Bundle.main
        if let frameworkPath = bundle.path(forResource: "Python", ofType: "framework", inDirectory: "Frameworks") {
            let libPath = "\(frameworkPath)/Versions/3.11/lib/libpython3.11.dylib"
            if FileManager.default.fileExists(atPath: libPath) {
                return libPath
            }
        }
        // Bundled framework not found — fail loudly rather than loading an untrusted dylib.
        return nil
    }

    private func getPythonSitePath() -> String? {
        let bundle = Bundle.main
        return bundle.path(forResource: "python_site", ofType: nil)
    }

    // MARK: - PythonServiceProtocol Implementation

    func executeOperation(_ operation: Data, reply: @escaping (Data?) -> Void) {
        workQueue.async { [weak self] in
            guard let self = self else {
                reply(self?.encodeError("Service deallocated"))
                return
            }

            guard self.pythonInitialized else {
                reply(self.encodeError("Python not initialized"))
                return
            }

            do {
                // Decode request
                let request = try JSONDecoder().decode(XPCRequestWrapper.self, from: operation)

                print("[PythonWorker] Executing operation: \(request.operation)")

                // Route to appropriate handler
                let resultData: Data
                switch request.operation {
                case "getPageCount":
                    resultData = try self.handleGetPageCount(parameters: request.parameters)

                case "identifyFont":
                    resultData = try self.handleIdentifyFont(parameters: request.parameters)

                case "replaceText":
                    resultData = try self.handleReplaceText(parameters: request.parameters)

                case "createMemento":
                    resultData = try self.handleCreateMemento(parameters: request.parameters)

                case "restoreFromMemento":
                    resultData = try self.handleRestoreFromMemento(parameters: request.parameters)

                default:
                    throw PythonWorkerError.unknownOperation(request.operation)
                }

                reply(resultData)

            } catch {
                print("[PythonWorker] ERROR: \(error)")
                reply(self.encodeError(error.localizedDescription))
            }
        }
    }

    func ping(reply: @escaping (Bool) -> Void) {
        reply(pythonInitialized)
    }

    func shutdown() {
        print("[PythonWorker] Shutdown requested")
        // Clean up Python resources
        pythonInitialized = false
        editorCore = nil
        pythonSys = nil
    }

    func getStatus(reply: @escaping ([String: Any]) -> Void) {
        let status: [String: Any] = [
            "pythonInitialized": pythonInitialized,
            "pythonVersion": pythonSys?["version"] as? String ?? "unknown",
            "editorCoreLoaded": editorCore != nil
        ]
        reply(status)
    }

    // MARK: - Operation Handlers

    private func handleGetPageCount(parameters: Data) throws -> Data {
        let params = try JSONDecoder().decode(GetPageCountParams.self, from: parameters)

        // Call Python
        guard let core = editorCore else {
            throw PythonWorkerError.pythonNotReady
        }

        let pageCount = Int(core.get_page_count(params.documentPath)) ?? 0

        let response = XPCResponseWrapper(
            id: UUID(),
            success: true,
            result: ["pageCount": pageCount],
            error: nil
        )

        return try JSONEncoder().encode(response)
    }

    private func handleIdentifyFont(parameters: Data) throws -> Data {
        let params = try JSONDecoder().decode(IdentifyFontParams.self, from: parameters)

        guard let core = editorCore else {
            throw PythonWorkerError.pythonNotReady
        }

        // Call Python core.identify_font()
        let pythonResult = core.identify_font(
            params.documentPath,
            params.pageIndex,
            params.targetText
        )

        // Convert Python dict to Swift FontDescriptor
        let fontDescriptor = try self.convertPythonFontDescriptor(pythonResult)

        let response = XPCResponseWrapper(
            id: UUID(),
            success: true,
            result: try fontDescriptor.asDictionary(),
            error: nil
        )

        return try JSONEncoder().encode(response)
    }

    private func handleReplaceText(parameters: Data) throws -> Data {
        let params = try JSONDecoder().decode(ReplaceTextParams.self, from: parameters)

        guard let core = editorCore else {
            throw PythonWorkerError.pythonNotReady
        }

        // Call Python core.replace_text()
        let pythonResult = core.replace_text(
            params.documentPath,
            params.targetText,
            params.replacementText,
            params.pageIndex,
            params.overrides.asPythonDict(),
            params.detectedFont?.asPythonDict() ?? Python.None,
            params.targetRect.asPythonDict()
        )

        // Convert result
        let result = try self.convertPythonReplaceResult(pythonResult)

        let response = XPCResponseWrapper(
            id: UUID(),
            success: true,
            result: try result.asDictionary(),
            error: nil
        )

        return try JSONEncoder().encode(response)
    }

    private func handleCreateMemento(parameters: Data) throws -> Data {
        let params = try JSONDecoder().decode(CreateMementoParams.self, from: parameters)

        guard let core = editorCore else {
            throw PythonWorkerError.pythonNotReady
        }

        // Call Python to extract content stream
        let pythonMemento = core.create_memento(
            params.documentPath,
            params.pageIndex,
            params.rect.asPythonDict()
        )

        let memento = try self.convertPythonMemento(pythonMemento)

        let response = XPCResponseWrapper(
            id: UUID(),
            success: true,
            result: try memento.asDictionary(),
            error: nil
        )

        return try JSONEncoder().encode(response)
    }

    private func handleRestoreFromMemento(parameters: Data) throws -> Data {
        let params = try JSONDecoder().decode(RestoreMementoParams.self, from: parameters)

        guard let core = editorCore else {
            throw PythonWorkerError.pythonNotReady
        }

        // Call Python to restore content stream
        let restoreResult = core.restore_from_memento(
            params.documentPath,
            params.memento.asPythonDict()
        )
        let restoredPath = String(restoreResult["output_path"]) ?? params.documentPath
        let success = Bool(restoreResult["success"]) ?? false
        let message = String(restoreResult["message"]) ?? "Restore failed"

        let response = XPCResponseWrapper(
            id: UUID(),
            success: success,
            result: ["restoredURL": restoredPath],
            error: success ? nil : ["message": message]
        )

        return try JSONEncoder().encode(response)
    }

    // MARK: - Conversion Helpers

    private func convertPythonFontDescriptor(_ pythonDict: PythonObject) throws -> FontDescriptorData {
        return FontDescriptorData(
            family: String(pythonDict["family"]) ?? "Unknown",
            postscriptName: String(pythonDict["postscript_name"]) ?? nil,
            weight: Int(pythonDict["weight"]) ?? 400,
            width: String(pythonDict["width"]) ?? "normal",
            slant: String(pythonDict["slant"]) ?? "normal",
            size: Double(pythonDict["size"]) ?? 12.0,
            xHeight: Double(pythonDict["x_height"]) ?? nil,
            capHeight: Double(pythonDict["cap_height"]) ?? nil
        )
    }

    private func convertPythonReplaceResult(_ pythonDict: PythonObject) throws -> ReplaceTextResultData {
        // Convert warnings array from Python
        var warnings: [String] = []
        let pythonWarnings = pythonDict["warnings"]
        if pythonWarnings != Python.None {
            let warningsCount = Int(pythonWarnings.__len__()) ?? 0
            for i in 0..<warningsCount {
                if let warning = String(pythonWarnings[i]) {
                    warnings.append(warning)
                }
            }
        }

        return ReplaceTextResultData(
            success: Bool(pythonDict["success"]) ?? false,
            modifiedDocumentPath: String(pythonDict["modified_path"]) ?? nil,
            appliedFont: FontDescriptorData(
                family: String(pythonDict["font_used"]) ?? "Helvetica",
                postscriptName: nil,
                weight: 400,
                width: "normal",
                slant: "normal",
                size: 12.0,
                xHeight: nil,
                capHeight: nil
            ),
            warnings: warnings,
            debugLog: [String(pythonDict["message"]) ?? ""].filter { !$0.isEmpty },
            instancesReplaced: Int(pythonDict["instances_replaced"]) ?? 0,
            executionTimeMs: 0.0
        )
    }

    private func convertPythonMemento(_ pythonDict: PythonObject) throws -> PDFMementoData {
        let x = Double(pythonDict["rect"]["x"]) ?? 0
        let y = Double(pythonDict["rect"]["y"]) ?? 0
        let width = Double(pythonDict["rect"]["width"]) ?? 0
        let height = Double(pythonDict["rect"]["height"]) ?? 0

        return PDFMementoData(
            pageIndex: Int(pythonDict["page_index"]) ?? 0,
            contentStream: String(pythonDict["content_stream"]) ?? "",
            affectedRect: CGRect(x: x, y: y, width: width, height: height)
        )
    }

    private func encodeError(_ message: String) -> Data? {
        let response = XPCResponseWrapper(
            id: UUID(),
            success: false,
            result: nil,
            error: ["message": message]
        )
        return try? JSONEncoder().encode(response)
    }
}

// MARK: - Error Types

enum PythonWorkerError: Error {
    case pythonNotReady
    case unknownOperation(String)
    case conversionFailed(String)
}

// MARK: - Message Types

struct XPCRequestWrapper: Codable {
    let id: UUID
    let operation: String
    let parameters: Data
    let timeout: TimeInterval
}

struct XPCResponseWrapper: Codable {
    let id: UUID
    let success: Bool
    let result: [String: Any]?
    let error: [String: String]?

    enum CodingKeys: String, CodingKey {
        case id, success, result, error
    }

    init(id: UUID, success: Bool, result: [String: Any]?, error: [String: String]?) {
        self.id = id
        self.success = success
        self.result = result
        self.error = error
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(UUID.self, forKey: .id)
        success = try container.decode(Bool.self, forKey: .success)
        // Propagate decode errors — using try? here would hide corrupt responses
        // where success==true but result is nil, masking the real failure.
        result = try container.decodeIfPresent([String: AnyCodable].self, forKey: .result)?.mapValues { $0.value }
        error = try container.decodeIfPresent([String: String].self, forKey: .error)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(success, forKey: .success)
        if let result = result {
            try container.encode(result.mapValues { AnyCodable($0) }, forKey: .result)
        }
        try container.encodeIfPresent(error, forKey: .error)
    }
}

// Helper for encoding Any values
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        // Int must be checked before Bool. Python's json module emits booleans as
        // literal true/false tokens, never 0/1. Swift's JSONDecoder will successfully
        // decode the JSON number 1 as Bool (via NSNumber bridging), so putting Bool
        // first would misclassify integer fields like page_number:1 or replacements:1.
        if let int = try? container.decode(Int.self) {
            value = int
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let bool as Bool:
            try container.encode(bool)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { AnyCodable($0) })
        case _ as NSNull:
            try container.encodeNil()
        default:
            try container.encodeNil()
        }
    }
}

// MARK: - Parameter Types

struct GetPageCountParams: Codable {
    let documentPath: String
}

struct IdentifyFontParams: Codable {
    let documentPath: String
    let pageIndex: Int
    let targetText: String
}

struct ReplaceTextParams: Codable {
    let documentPath: String
    let targetText: String
    let replacementText: String
    let pageIndex: Int
    let overrides: TextOverridesData
    let detectedFont: FontDescriptorData?
    let targetRect: CGRectData
}

struct CreateMementoParams: Codable {
    let documentPath: String
    let pageIndex: Int
    let rect: CGRectData
}

struct RestoreMementoParams: Codable {
    let documentPath: String
    let memento: PDFMementoData
}

// MARK: - Data Transfer Types

struct FontDescriptorData: Codable {
    let family: String
    let postscriptName: String?
    let weight: Int
    let width: String
    let slant: String
    let size: Double
    let xHeight: Double?
    let capHeight: Double?

    func asDictionary() throws -> [String: Any] {
        let data = try JSONEncoder().encode(self)
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }

    func asPythonDict() -> PythonObject {
        let pythonDict = PythonObject([:])
        pythonDict["family"] = PythonObject(family)
        pythonDict["weight"] = PythonObject(weight)
        pythonDict["width"] = PythonObject(width)
        pythonDict["slant"] = PythonObject(slant)
        pythonDict["size"] = PythonObject(size)
        if let ps = postscriptName { pythonDict["postscript_name"] = PythonObject(ps) }
        if let xh = xHeight { pythonDict["x_height"] = PythonObject(xh) }
        if let ch = capHeight { pythonDict["cap_height"] = PythonObject(ch) }
        return pythonDict
    }
}

struct TextOverridesData: Codable {
    let fontName: String?
    let fontStyle: String?
    let isBold: Bool
    let isItalic: Bool
    let sizeDelta: Double
    let xOffset: Double
    let yOffset: Double
    let trackingDelta: Double
    let fillColor: String?
    let justification: String?
    let skipVisualMatching: Bool

    func asPythonDict() -> PythonObject {
        let pythonDict = PythonObject([:])
        if let fontName { pythonDict["fontName"] = PythonObject(fontName) }
        if let fontStyle { pythonDict["fontStyle"] = PythonObject(fontStyle) }
        pythonDict["isBold"] = PythonObject(isBold)
        pythonDict["isItalic"] = PythonObject(isItalic)
        pythonDict["sizeDelta"] = PythonObject(sizeDelta)
        pythonDict["xOffset"] = PythonObject(xOffset)
        pythonDict["yOffset"] = PythonObject(yOffset)
        pythonDict["trackingDelta"] = PythonObject(trackingDelta)
        if let fillColor { pythonDict["fillColor"] = PythonObject(fillColor) }
        if let justification { pythonDict["justification"] = PythonObject(justification) }
        pythonDict["skipVisualMatching"] = PythonObject(skipVisualMatching)
        return pythonDict
    }
}

struct CGRectData: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double

    init(from rect: CGRect) {
        self.x = rect.origin.x
        self.y = rect.origin.y
        self.width = rect.size.width
        self.height = rect.size.height
    }

    func asCGRect() -> CGRect {
        return CGRect(x: x, y: y, width: width, height: height)
    }

    func asPythonDict() -> PythonObject {
        return PythonObject([
            "x": x,
            "y": y,
            "width": width,
            "height": height
        ])
    }

    func asDictionary() throws -> [String: Any] {
        return ["x": x, "y": y, "width": width, "height": height]
    }
}

struct ReplaceTextResultData: Codable {
    let success: Bool
    let modifiedDocumentPath: String?
    let appliedFont: FontDescriptorData
    let warnings: [String]
    let debugLog: [String]
    let instancesReplaced: Int
    let executionTimeMs: Double

    func asDictionary() throws -> [String: Any] {
        var dict: [String: Any] = [
            "success": success,
            "warnings": warnings,
            "appliedFont": try appliedFont.asDictionary(),
            "debugLog": debugLog,
            "instancesReplaced": instancesReplaced,
            "executionTimeMs": executionTimeMs
        ]
        if let path = modifiedDocumentPath {
            dict["modifiedDocumentPath"] = path
        }
        return dict
    }
}

struct PDFMementoData: Codable {
    let pageIndex: Int
    let contentStream: String
    let affectedRect: CGRect

    enum CodingKeys: String, CodingKey {
        case pageIndex, contentStream, affectedRect
    }

    init(pageIndex: Int, contentStream: String, affectedRect: CGRect) {
        self.pageIndex = pageIndex
        self.contentStream = contentStream
        self.affectedRect = affectedRect
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        pageIndex = try container.decode(Int.self, forKey: .pageIndex)
        contentStream = try container.decode(String.self, forKey: .contentStream)

        let rectData = try container.decode(CGRectData.self, forKey: .affectedRect)
        affectedRect = rectData.asCGRect()
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(pageIndex, forKey: .pageIndex)
        try container.encode(contentStream, forKey: .contentStream)
        try container.encode(CGRectData(from: affectedRect), forKey: .affectedRect)
    }

    func asDictionary() throws -> [String: Any] {
        return [
            "pageIndex": pageIndex,
            "contentStream": contentStream,
            "affectedRect": [
                "x": affectedRect.origin.x,
                "y": affectedRect.origin.y,
                "width": affectedRect.size.width,
                "height": affectedRect.size.height
            ]
        ]
    }

    func asPythonDict() -> PythonObject {
        let pythonDict = PythonObject([:])
        pythonDict["page_index"] = PythonObject(pageIndex)
        pythonDict["content_stream"] = PythonObject(contentStream)

        let rectDict = PythonObject([:])
        rectDict["x"] = PythonObject(Double(affectedRect.origin.x))
        rectDict["y"] = PythonObject(Double(affectedRect.origin.y))
        rectDict["width"] = PythonObject(Double(affectedRect.size.width))
        rectDict["height"] = PythonObject(Double(affectedRect.size.height))
        pythonDict["rect"] = rectDict

        return pythonDict
    }
}
