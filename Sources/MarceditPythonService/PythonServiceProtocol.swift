//
//  PythonServiceProtocol.swift
//  MarceditPythonService
//
//  Created: 2026-01-23
//  Purpose: XPC protocol for Python operations in separate process
//

import Foundation

/// Protocol for XPC communication between main app and Python service
@objc protocol PythonServiceProtocol {

    /// Execute a Python operation with encoded request/response
    /// - Parameters:
    ///   - operation: Encoded XPCRequest as JSON Data
    ///   - reply: Completion handler with encoded XPCResponse as JSON Data
    func executeOperation(
        _ operation: Data,
        reply: @escaping (Data?) -> Void
    )

    /// Ping the service to check if it's alive
    /// - Parameter reply: Completion handler with true if service is running
    func ping(reply: @escaping (Bool) -> Void)

    /// Shutdown the service gracefully
    func shutdown()

    /// Get service status information
    /// - Parameter reply: Completion handler with status dictionary
    func getStatus(reply: @escaping ([String: Any]) -> Void)
}
