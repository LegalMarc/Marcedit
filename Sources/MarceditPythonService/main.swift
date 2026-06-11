//
//  main.swift
//  MarceditPythonService
//
//  Created: 2026-01-23
//  Purpose: XPC service entry point for Python operations
//

import Foundation

/// Delegate for handling XPC connections
class PythonServiceDelegate: NSObject, NSXPCListenerDelegate {

    func listener(
        _ listener: NSXPCListener,
        shouldAcceptNewConnection newConnection: NSXPCConnection
    ) -> Bool {
        print("[PythonService] New connection from PID: \(newConnection.processIdentifier)")

        // Verify the connecting process is signed by the same team as this service
        // and carries the main app's bundle identifier.  This prevents any other
        // local process from driving file operations with the app's privileges.
        // Skipped in DEBUG builds — ad-hoc/unsigned debug builds lack an Apple anchor
        // and would silently fail the XPC connection, breaking the Python backend.
        #if !DEBUG
        var requirement = "anchor apple generic and identifier \"com.marclaw.Marcedit\""
        // If AppTeamID is present in the service bundle's Info.plist, tighten the
        // requirement to the team OU so a legitimately-identified but differently-
        // signed binary is still rejected.  The Info.plist ships with a
        // $(DEVELOPMENT_TEAM) placeholder; Xcode substitutes the real team ID when
        // the target is built under a signed provisioning profile.
        if let teamID = Bundle.main.object(forInfoDictionaryKey: "AppTeamID") as? String,
           !teamID.isEmpty {
            requirement += " and certificate leaf[subject.OU] = \"\(teamID)\""
        }
        do {
            try newConnection.setCodeSigningRequirement(requirement)
        } catch {
            print("[PythonService] Connection rejected: code signing requirement failed — \(error)")
            return false
        }
        #endif

        newConnection.exportedInterface = NSXPCInterface(with: PythonServiceProtocol.self)
        newConnection.exportedObject = PythonWorker()

        newConnection.invalidationHandler = {
            print("[PythonService] Connection invalidated")
        }
        newConnection.interruptionHandler = {
            print("[PythonService] Connection interrupted")
        }

        newConnection.resume()
        print("[PythonService] Connection accepted and resumed")
        return true
    }
}

// MARK: - Service Entry Point

print("[PythonService] Starting Marcedit Python Service...")
print("[PythonService] Process ID: \(ProcessInfo.processInfo.processIdentifier)")

let delegate = PythonServiceDelegate()
let listener = NSXPCListener.service()
listener.delegate = delegate

print("[PythonService] Listener configured, resuming...")
listener.resume()

// Run the service indefinitely
RunLoop.main.run()
