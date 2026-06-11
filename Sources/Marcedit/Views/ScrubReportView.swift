import SwiftUI
import WebKit

/// View to display the metadata scrub report in a WebView
struct ScrubReportView: View {
    let reportURL: URL
    let onDismiss: () -> Void
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Metadata Scrub Report")
                    .font(.headline)
                
                Spacer()
                
                Button(action: revealInFinder) {
                    Label("Reveal in Finder", systemImage: "folder")
                }
                .buttonStyle(.bordered)
                
                Button("Done") {
                    onDismiss()
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
            .background(Color(nsColor: .windowBackgroundColor))
            
            Divider()
            
            // WebView for HTML report
            WebViewWrapper(url: reportURL)
        }
        .frame(minWidth: 600, idealWidth: 800, maxWidth: .infinity,
               minHeight: 400, idealHeight: 600, maxHeight: .infinity)
    }
    
    private func revealInFinder() {
        NSWorkspace.shared.activateFileViewerSelecting([reportURL])
    }
}

/// NSViewRepresentable wrapper for WKWebView
struct WebViewWrapper: NSViewRepresentable {
    let url: URL
    
    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = false

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        return webView
    }
    
    func updateNSView(_ webView: WKWebView, context: Context) {
        webView.loadFileURL(url, allowingReadAccessTo: url)
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        // Handle navigation events if needed
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Allow all navigation within local files
            if let url = navigationAction.request.url {
                if url.isFileURL {
                    decisionHandler(.allow)
                } else {
                    // Open external URLs in default browser
                    NSWorkspace.shared.open(url)
                    decisionHandler(.cancel)
                }
            } else {
                decisionHandler(.allow)
            }
        }
    }
}

// MARK: - Window-based Report Presentation

/// Controller to manage the report window lifecycle
class ReportWindowController {
    static var activeWindows: [NSWindow] = []
    
    /// Opens the scrub report in a separate, movable/resizable window
    static func openReportWindow(for reportURL: URL) {
        let contentView = ScrubReportView(reportURL: reportURL) {
            // onDismiss - close window
            if let window = NSApp.keyWindow, activeWindows.contains(window) {
                window.close()
            }
        }
        
        let hostingView = NSHostingView(rootView: contentView)
        
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 800, height: 600),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        
        window.title = "Metadata Report - \(reportURL.deletingPathExtension().lastPathComponent)"
        window.contentView = hostingView
        window.center()
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 500, height: 400)
        
        // Keep strong reference
        activeWindows.append(window)
        
        // Remove from array when closed
        NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification,
            object: window,
            queue: .main
        ) { _ in
            activeWindows.removeAll { $0 == window }
        }
        
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

#Preview {
    ScrubReportView(
        reportURL: URL(fileURLWithPath: "/tmp/test_report.html"),
        onDismiss: {}
    )
}
