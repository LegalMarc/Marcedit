import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    static var pythonRunner: PythonRunnerProtocol?
    static weak var shared: AppDelegate? // Allow access to instance

    private var isPythonInitializationInProgress = false

    // Callback to check if app can terminate (returns false when unsaved changes exist)
    var terminationCheck: (() -> Bool)?
    // Callback to check whether a Python operation is in flight
    var isProcessingCheck: (() -> Bool)?
    // Callback to check whether a secure erase is currently running (non-cancellable)
    var isErasureInProgressCheck: (() -> Bool)?
    // Callback to cancel any in-flight processing task on forced quit or app termination
    var cancelProcessingCallback: (() -> Void)?
    
    override init() {
        super.init()
        AppDelegate.shared = self
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppDelegate.shared = self
        print("AppDelegate: applicationDidFinishLaunching called")
        initializePythonRuntimeIfNeeded()
        TestBridge.setup()  // No-op unless launched with --run-ui-tests
    }

    func initializePythonRuntimeIfNeeded() {
        guard AppDelegate.pythonRunner == nil, !isPythonInitializationInProgress else { return }
        isPythonInitializationInProgress = true
        let startTime = Date()

        do {
            let runner = try PythonKitRunner(logger: { msg in
                print("PythonRuntime: \(msg)")
                LogManager.shared.log("PythonRuntime: \(msg)")
            })
            AppDelegate.pythonRunner = runner
            let elapsed = Date().timeIntervalSince(startTime)
            print(String(format: "Python runtime initialized (%.2fs)", elapsed))
            LogManager.shared.log(String(format: "Python runtime initialized (%.2fs)", elapsed))
            
            // Validate environment - check if all required modules can be imported
            let validation = runner.validateEnvironment()
            if validation.success {
                LogManager.shared.log("✓ \(validation.message)")
            } else {
                LogManager.shared.log("⚠ Python validation failed: \(validation.message)", level: .error)
                print("⚠ Python validation failed: \(validation.message)")
            }
        } catch {
            let elapsed = Date().timeIntervalSince(startTime)
            print("Python init failed (\(String(format: "%.2fs", elapsed))): \(error)")
            LogManager.shared.log("Python init failed: \(error)", level: .error)
        }

        isPythonInitializationInProgress = false
    }
    
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        LogManager.shared.log("App: applicationShouldTerminate called")

        // Block termination if a secure erase is running — this is non-cancellable.
        // Destroying and overwriting files is irreversible; a partial erase would leave
        // inconsistent state. Do not offer "Quit Anyway".
        if let erasureCheck = isErasureInProgressCheck, erasureCheck() {
            LogManager.shared.log("App: cancelling termination — secure erase in progress (non-cancellable)")
            let alert = NSAlert()
            alert.messageText = "Secure Erase in Progress"
            alert.informativeText = "A secure erase is in progress and cannot be interrupted. Please wait for it to complete before quitting."
            alert.alertStyle = .warning
            alert.addButton(withTitle: "OK")
            alert.runModal()
            return .terminateCancel
        }

        // Block termination if a cancellable Python operation is in flight
        if let processingCheck = isProcessingCheck, processingCheck() {
            LogManager.shared.log("App: cancelling termination — Python operation in progress")
            let alert = NSAlert()
            alert.messageText = "Operation in Progress"
            alert.informativeText = "A PDF operation is in progress. Please wait for it to complete before quitting."
            alert.alertStyle = .warning
            alert.addButton(withTitle: "Cancel")
            let quitAnywayButton = alert.addButton(withTitle: "Quit Anyway")
            quitAnywayButton.hasDestructiveAction = true
            let response = alert.runModal()
            if response == .alertSecondButtonReturn {
                // User chose "Quit Anyway" — cancel the in-flight task and proceed
                LogManager.shared.log("App: user chose Quit Anyway during processing — cancelling task")
                cancelProcessingCallback?()
                return .terminateNow
            }
            return .terminateCancel
        }

        if let check = terminationCheck {
            let canTerminate = check()
            LogManager.shared.log("App: terminationCheck result: \(canTerminate)")
            if !canTerminate {
                LogManager.shared.log("App: cancelling termination for unsaved changes")
                NotificationCenter.default.post(name: .attemptToCloseApp, object: nil)
                return .terminateCancel
            }
        } else {
            LogManager.shared.log("App: terminationCheck is NIL - allowing quit", level: .error)
        }
        return .terminateNow
    }

    func applicationWillTerminate(_ notification: Notification) {
        LogManager.shared.log("App: applicationWillTerminate — cancelling any in-flight processing task")
        cancelProcessingCallback?()
    }
}
