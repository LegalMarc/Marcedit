import SwiftUI

struct AboutView: View {
    @Environment(\.colorScheme) private var colorScheme
    
    private var backgroundColor: Color {
        colorScheme == .dark ? Color(red: 0.08, green: 0.08, blue: 0.14) : Color(nsColor: .windowBackgroundColor)
    }
    
    var body: some View {
        VStack(spacing: 12) {
            // App Icon
            Image(nsImage: NSApp.applicationIconImage)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 64, height: 64)

            // App Name
            Text("Marcedit")
                .font(.title)
                .fontWeight(.bold)

            // Version (dynamic from bundle) - shows X.Y.Z format
            Text("Version \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")")
                .font(.body)

            // Copyright
            Text("Copyright © 2025 Marc Mandel.")
                .font(.body)
                .foregroundColor(.secondary)
                .padding(.bottom, 8)

            Divider()

            // Custom Text
            VStack {
                Text("For privacy and security reasons, this application will never connect to the Internet. To be notified of updates, email apps@marclaw.com.")
            }
            .font(.body)
            .multilineTextAlignment(.center)
            .foregroundColor(.secondary)

        }
        .padding(24)
        .frame(width: 350)
        .background(backgroundColor)
    }
} 

