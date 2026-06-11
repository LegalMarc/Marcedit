# Marcedit Architecture Status

Marcedit currently has two SwiftUI-facing view-model paths:

- `EditorViewModel` is the active compatibility path used by the existing views.
- `EditorViewModelV2` bridges the newer `DocumentCoordinator` architecture but remains a migration layer, not the only production path.

Public-beta changes should keep behavior aligned across both paths when they touch shared UI state, caches, document lifecycle, or undo/redo expectations. New work should prefer the coordinator architecture for isolated services, but should not remove the legacy path until the UI is fully migrated and covered by focused XCUITests.

## Operational notes

- The legacy path still owns the main edit workflow and has explicit bounds on edit history and font-search cache growth.
- The V2 path delegates command history to `DocumentCoordinator`, which already has a bounded undo stack and command cleanup.
- Generated visual and GUI artifacts are local-only by default. External evaluator APIs and full-screen screenshot capture require explicit environment opt-in.
