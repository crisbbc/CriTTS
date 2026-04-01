# voice-auto-select-on-provider-switch Specification

## Purpose
TBD - created by archiving change fix-provider-voice-on-switch. Update Purpose after archive.
## Requirements
### Requirement: Voice list reloads immediately when provider changes
When the user selects a different TTS provider in the TTS Provider settings tab, the Voice tab SHALL immediately begin reloading the voice list for the newly selected provider without requiring the user to save settings and reopen the Settings window.

#### Scenario: Switching from Edge TTS to Piper TTS reloads voice list
- **WHEN** the user changes the TTS provider dropdown from "Edge TTS (Online)" to "Piper TTS (Offline)"
- **THEN** the Voice tab's voice dropdown SHALL be populated with Piper voices once the async load completes

#### Scenario: Switching from Piper TTS to Edge TTS reloads voice list
- **WHEN** the user changes the TTS provider dropdown from "Piper TTS (Offline)" to "Edge TTS (Online)"
- **THEN** the Voice tab's voice dropdown SHALL be populated with Edge TTS voices once the async load completes

#### Scenario: Loading indicator shown during reload
- **WHEN** a provider switch triggers a voice list reload
- **THEN** the voice dropdown SHALL display a loading placeholder (e.g. "Loading…") while the async fetch is in progress

### Requirement: A valid provider voice is auto-selected after provider switch
After the voice list reloads in response to a provider change, the system SHALL automatically select a valid voice from the new provider's list so that saving settings produces a consistent `voice` value.

#### Scenario: Default voice selected when saved voice not in new provider list
- **WHEN** the voice list reloads for a new provider
- **AND** the previously saved voice ID does not exist in the new provider's voice list
- **THEN** the first available voice in the new provider's list SHALL be selected automatically

#### Scenario: Settings saved immediately after provider switch contain a valid voice
- **WHEN** the user switches provider and saves without manually picking a voice
- **THEN** the saved `voice` setting SHALL be a valid voice ID for the newly selected provider

