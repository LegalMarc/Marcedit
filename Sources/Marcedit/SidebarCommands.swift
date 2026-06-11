import SwiftUI

// MARK: - Focused Value Key
struct SidebarCollapsedKey: FocusedValueKey {
    typealias Value = Binding<Bool>
}

extension FocusedValues {
    var sidebarCollapsed: Binding<Bool>? {
        get { self[SidebarCollapsedKey.self] }
        set { self[SidebarCollapsedKey.self] = newValue }
    }
}

// MARK: - Menu Commands
struct SidebarCommands: Commands {
    @FocusedBinding(\.sidebarCollapsed) var isCollapsed
    
    var body: some Commands {
        CommandGroup(after: .sidebar) {
            Button(action: {
                isCollapsed?.toggle()
            }) {
                Label(isCollapsed == true ? "Show Command Panel" : "Hide Command Panel", systemImage: "sidebar.left")
            }
            .keyboardShortcut("b", modifiers: .command)
            .disabled(isCollapsed == nil)
        }
    }
}
