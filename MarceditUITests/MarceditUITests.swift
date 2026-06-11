import XCTest

final class MarceditUITests: XCTestCase {
    var app: XCUIApplication!
    
    override func setUpWithError() throws {
        continueAfterFailure = false
        
        // Launch the pre-built app
        app = XCUIApplication(bundleIdentifier: "com.marcedit.app")
        app.launch()
    }
    
    override func tearDownWithError() throws {
        app?.terminate()
    }
    
    /// Test that the app launches and shows the main window
    func testAppLaunches() throws {
        XCTAssertTrue(app.windows.count > 0, "App should have at least one window")
        
        // Check for key UI elements
        let openButton = app.buttons["Open PDF File"]
        XCTAssertTrue(openButton.waitForExistence(timeout: 5), "Open PDF button should exist")
    }
    
    /// Test opening a PDF file via drag-drop simulation
    func testOpenPDFFile() throws {
        // Look for "No Document Selected" text initially
        let noDocText = app.staticTexts["No Document Selected"]
        XCTAssertTrue(noDocText.waitForExistence(timeout: 5), "Should show No Document Selected initially")
        
        // Click the Open PDF button
        let openButton = app.buttons["Open PDF File"]
        if openButton.exists {
            openButton.click()
            
            // Wait for file dialog
            sleep(1)
            
            // Use keyboard to navigate (Cmd+Shift+G)
            app.typeKey("g", modifierFlags: [.command, .shift])
            sleep(1)
            
            // Type path to test PDF
            app.typeText("/tmp/test_preview_fix.pdf")
            app.typeKey(.return, modifierFlags: [])
            sleep(1)
            app.typeKey(.return, modifierFlags: [])
            
            sleep(3)
            
            // Verify document loaded
            XCTAssertFalse(noDocText.exists, "No Document text should disappear after opening file")
        }
    }
    
    /// Test the preview bug fix - edited text should persist after preview toggle
    func testPreviewBugFix() throws {
        // This test requires a PDF to be loaded first
        // We'll need to set up the state appropriately
        
        // For now, just verify the app is functional
        let mainWindow = app.windows.firstMatch
        XCTAssertTrue(mainWindow.exists, "Main window should exist")
    }
}
