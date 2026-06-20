## ADDED Requirements

### Requirement: Description labels update wraplength on resize
All description/hint labels in the settings tabs (created via `BaseTab.create_description()`) SHALL update their `wraplength` dynamically whenever the right-side scroll pane is resized. The `wraplength` SHALL be set to the scroll pane's current inner width minus a fixed padding constant (32px).

#### Scenario: Text wraps at new width after narrowing window
- **WHEN** the user resizes the settings window to a narrower width
- **THEN** all visible description labels in the active tab reflow their text to fit the new scroll pane width without overflow

#### Scenario: Text uses available width after widening window
- **WHEN** the user resizes the settings window to a wider width
- **THEN** description labels expand their wraplength to use the available space

#### Scenario: Wraplength updated on initial layout
- **WHEN** the settings window is first displayed
- **THEN** all description labels are already sized to the actual scroll pane width (not the hardcoded 550px fallback)

### Requirement: Dropdown widgets expand to fill available width
Dropdown widgets whose pack options include `fill="x"` or `expand=True` SHALL NOT declare a fixed pixel `width`. Removing the fixed `width` attribute allows CTk to respect the fill/expand geometry manager options.

#### Scenario: Device dropdown expands in Audio Output tab
- **WHEN** the settings window is resized wider
- **THEN** the device dropdown in the Audio Output tab stretches to fill the available width

#### Scenario: Voice dropdown expands in Voice tab
- **WHEN** the settings window is resized wider
- **THEN** the voice dropdown in the Voice tab stretches to fill the available width
