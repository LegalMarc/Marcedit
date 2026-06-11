// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Marcedit",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "Marcedit", targets: ["Marcedit"]),
        .executable(name: "MarceditPythonService", targets: ["MarceditPythonService"])
    ],
    dependencies: [
        .package(url: "https://github.com/pvieito/PythonKit.git", from: "0.5.1")

    ],
    targets: [
        .executableTarget(
            name: "Marcedit",
            dependencies: [
                .product(name: "PythonKit", package: "PythonKit")
            ],
            path: "Sources/Marcedit",
            exclude: ["Info.plist", "Marcedit.entitlements"],
            resources: [
                .process("Assets.xcassets"),
                .copy("Frameworks"),
                .copy("python_site"),
                .copy("Resources")
            ]
        ),
        .executableTarget(
            name: "MarceditPythonService",
            dependencies: [
                .product(name: "PythonKit", package: "PythonKit")
            ],
            path: "Sources/MarceditPythonService"
        ),
        .testTarget(
            name: "MarceditTests",
            dependencies: ["Marcedit"],
            path: "Tests/MarceditTests"
        )
    ]
)
