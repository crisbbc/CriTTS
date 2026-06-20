## ADDED Requirements

### Requirement: Apply button saves settings without closing window
The settings window SHALL include an **Apply** button positioned to the right of the Save button in the button bar. Clicking Apply SHALL persist all current settings to disk and keep the settings window open.

#### Scenario: Apply saves without closing
- **WHEN** the user clicks the Apply button
- **THEN** all tab settings are validated, saved to disk, and the settings window remains open

#### Scenario: Apply shows no UI change on success
- **WHEN** the user clicks Apply and validation passes
- **THEN** the window stays open with no error dialog and no visual disruption

#### Scenario: Apply shows error on validation failure
- **WHEN** the user clicks Apply and validation fails
- **THEN** an error dialog is shown and the window remains open with no settings written to disk

### Requirement: Validate settings before mutating in-memory state
The settings window SHALL validate all tab settings before writing any value into the in-memory `SettingsManager`. No in-memory state SHALL be mutated if validation fails.

#### Scenario: Failed validation leaves memory clean
- **WHEN** the user clicks Save (or Apply) and validation fails
- **THEN** the in-memory `SettingsManager` retains the values from the last successful save

#### Scenario: Successful validation applies all values
- **WHEN** validation passes on Save or Apply
- **THEN** all collected tab settings are written into `SettingsManager` and then persisted to disk

### Requirement: X-button close behaves as Cancel
The settings window SHALL bind the `WM_DELETE_WINDOW` protocol to the same handler as the Cancel button so that closing with the window X-button does not leak dirty in-memory state.

#### Scenario: X-button cancels without saving
- **WHEN** the user closes the settings window via the OS X button
- **THEN** no settings are written to disk and in-memory state is unchanged
