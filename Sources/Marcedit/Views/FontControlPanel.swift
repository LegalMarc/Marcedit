import SwiftUI
import AppKit

struct FontControlPanel: View {
    @ObservedObject var vm: EditorViewModelV2

    var body: some View {
        VStack(spacing: 12) {
            Text("Text Controls")
                .font(.headline)
                .frame(maxWidth: .infinity, alignment: .leading)

            Divider()

            selectionModeSection

            Divider()

            controlsSection
        }
        .padding(12)
        // Card styling handled by parent container
    }

    // MARK: - Component Sections

    @ViewBuilder
    private var selectionModeSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Text Selection")
                .font(.caption).fontWeight(.medium)

            Text("Click a line to select it, or drag across text to select multiple lines.")
                .font(.caption2)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private var controlsSection: some View {
        VStack(spacing: 6) {
            Text("⌘ for 10× steps")
                .font(.caption2).foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)

            // Nudge row: label + value + ↑↓ ←→
            HStack {
                Text("Nudge").font(.caption).foregroundColor(.secondary)
                Spacer()
                Text(String(format: "%+.1f, %+.1f", vm.manualOverrides.xOffset, vm.manualOverrides.yOffset))
                    .font(.caption).monospacedDigit()
                ArrowButton(icon: "arrow.up") { cmd in nudge("up", withCommand: cmd) }
                    .accessibilityIdentifier("NudgeButtonUp")
                ArrowButton(icon: "arrow.down") { cmd in nudge("down", withCommand: cmd) }
                    .accessibilityIdentifier("NudgeButtonDown")
                ArrowButton(icon: "arrow.left") { cmd in nudge("left", withCommand: cmd) }
                    .accessibilityIdentifier("NudgeButtonLeft")
                ArrowButton(icon: "arrow.right") { cmd in nudge("right", withCommand: cmd) }
                    .accessibilityIdentifier("NudgeButtonRight")
            }

            // Size row: label + value + ↑↓
            HStack {
                Text("Size").font(.caption).foregroundColor(.secondary)
                Spacer()
                Text(String(format: "%+.1f", vm.manualOverrides.sizeDelta))
                    .font(.caption).monospacedDigit()
                ArrowButton(icon: "arrow.up") { cmd in nudge("size_up", withCommand: cmd) }
                    .accessibilityIdentifier("SizeUp")
                ArrowButton(icon: "arrow.down") { cmd in nudge("size_down", withCommand: cmd) }
                    .accessibilityIdentifier("SizeDown")
            }

            // Kern row: label + value + ←→
            HStack {
                Text("Kern").font(.caption).foregroundColor(.secondary)
                Spacer()
                Text(String(format: "%+.2f", vm.manualOverrides.trackingDelta))
                    .font(.caption).monospacedDigit()
                ArrowButton(icon: "arrow.left") { cmd in nudge("kern_down", withCommand: cmd) }
                    .accessibilityIdentifier("KernDown")
                ArrowButton(icon: "arrow.right") { cmd in nudge("kern_up", withCommand: cmd) }
                    .accessibilityIdentifier("KernUp")
            }
        }
    }

    // MARK: - Helpers

    private func nudge(_ dir: String, withCommand: Bool = false) {
        var val = withCommand ? 1.0 : 0.1
        if dir.contains("kern") { val = withCommand ? 0.5 : 0.05 }
        vm.nudge(direction: dir, amount: val)
    }
}

// MARK: - Arrow Button

/// A small arrow button that checks ⌘ on click and supports press-and-hold with acceleration.
struct ArrowButton: View {
    let icon: String
    let action: (Bool) -> Void  // Bool = isCommandPressed

    @State private var timer: Timer?
    @State private var repeatCount = 0
    @State private var isPressed = false

    private let schedule: [(threshold: Int, interval: TimeInterval)] = [
        (0, 0.3),
        (5, 0.15),
        (10, 0.08),
        (20, 0.05)
    ]

    var body: some View {
        Button(action: {}) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .medium))
                .frame(width: 22, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
        .background(isPressed ? Color(NSColor.selectedControlColor).opacity(0.3) : Color.clear)
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    if !isPressed {
                        isPressed = true
                        startRepeating()
                    }
                }
                .onEnded { _ in
                    stopRepeating()
                }
        )
        .onDisappear {
            stopRepeating()
        }
    }

    private func startRepeating() {
        let cmd = NSEvent.modifierFlags.contains(.command)
        action(cmd)
        repeatCount = 1
        scheduleNextRepeat()
    }

    private func scheduleNextRepeat() {
        var interval: TimeInterval = 0.3
        for (threshold, int) in schedule {
            if repeatCount >= threshold {
                interval = int
            }
        }

        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [self] _ in
            if isPressed {
                let cmd = NSEvent.modifierFlags.contains(.command)
                action(cmd)
                repeatCount += 1
                scheduleNextRepeat()
            }
        }
    }

    private func stopRepeating() {
        isPressed = false
        timer?.invalidate()
        timer = nil
        repeatCount = 0
    }
}
