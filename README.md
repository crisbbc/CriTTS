# CriTTS Recoded

A modern, free Text-to-Speech (TTS) application with a beautiful dark mode GUI. CriTTS Recoded uses Microsoft Edge's TTS engine (via edge_tts) to generate high-quality speech and can route audio to any output device, including virtual cables for Discord integration.

## Features

- **Free TTS Engine**: Uses Microsoft Edge's online TTS service (no API key required)
- **100+ Voices**: Access to all Microsoft Edge voices in multiple languages
- **Audio Routing**: Route TTS output to any audio device (including VB-Cable for Discord)
- **Modern Dark Mode GUI**: Built with CustomTkinter for a sleek, modern interface
- **Voice Customization**: Adjust speech rate, volume, and pitch
- **High-Quality Audio**: Support for 48kHz/192kbps and lossless PCM formats
- **Audio Normalization**: Peak and RMS normalization for consistent volume
- **Professional Audio Processing**: Anti-aliasing resampling and stereo enhancement
- **Persistent Settings**: Saves your preferences between sessions
- **Keyboard Shortcuts**: Ctrl+Enter to speak, Escape to stop, Ctrl+T to clear

## Audio Quality Settings

CriTTS Recoded now supports professional-grade audio quality with multiple presets and advanced processing options.

### Quality Presets

Access these in Settings > Audio Quality:

| Preset | Format | Sample Rate | Bitrate | Best For |
|--------|--------|-------------|---------|----------|
| **Maximum** | Lossless PCM | 48kHz | Lossless | Short texts, maximum fidelity |
| **High** | MP3 | 48kHz | 192kbps | General use, recommended |
| **Medium** | MP3 | 48kHz | 96kbps | Good balance, longer texts |
| **Low** | MP3 | 24kHz | 48kbps | Slow connections, quick previews |

### Advanced Options

- **Audio Normalization**: Choose between Peak (prevents clipping), RMS (consistent loudness), LUFS (professional loudness standards), or None
- **Enable Normalization**: Toggle normalization on/off
- **Stereo Enhancement**: Automatic mono-to-stereo conversion with width enhancement

### Audio Normalization Options

CriTTS Recoded offers three normalization types to ensure optimal audio quality:

| Type | Description | Best For | Technical Details |
|------|-------------|----------|-------------------|
| **Peak** | Prevents clipping by limiting maximum amplitude to -1dB | General use, speech | Targets 0.891 amplitude (-1dB), safe headroom |
| **RMS** | Ensures consistent loudness across different voices | Multi-voice projects | Targets 0.15 RMS level, 10x gain limit |
| **LUFS** | Professional loudness standards (requires pyloudnorm) | Streaming/broadcast | -14 LUFS (streaming) or -23 LUFS (broadcast) |
| **None** | No processing | Custom audio workflows | Bypasses normalization entirely |

**When to Use Each:**
- **Peak**: Default choice for most users, prevents distortion
- **RMS**: Use when voices have varying loudness levels
- **LUFS**: Professional content for YouTube, Spotify, or broadcast
- **None**: When using external audio processing software

**Note:** LUFS normalization requires the `pyloudnorm` library. If not installed, it falls back to Peak normalization.

### When to Use Each Preset

- **Maximum (Lossless)**: Use for important presentations, audiobooks, or when you need the absolute best quality. Note: Uses more memory, best for shorter texts.
- **High (192kbps)**: The recommended default for most users. Excellent quality with good performance.
- **Medium (96kbps)**: Good for longer texts or when you want to save bandwidth.
- **Low (48kbps)**: Useful for quick testing or when on a slow connection.

### Audio Processing Pipeline

The audio pipeline includes:
1. **High-Quality Resampling**: Uses scipy's polyphase resampling with anti-aliasing filters
2. **Normalization**: Prevents clipping and ensures consistent volume
3. **Stereo Enhancement**: Converts mono TTS output to natural-sounding stereo

## VRChat Integration

CriTTS Recoded includes built-in VRChat integration that automatically speaks incoming chat messages from other players using TTS.

### ⚠️ Important Limitation

**VRChat integration only monitors INCOMING messages from OTHER players.** Your own typed messages in VRChat are **NOT** logged by VRChat and cannot be detected by CriTTS. This is a VRChat limitation, not a CriTTS bug.

### Quick Start

1. Open **Settings** > **VR Mode** tab
2. Check **"Enable VRChat Mode"**
3. Configure log path (auto-detect usually works)
4. Set message filters as desired
5. Click **Save**

### Features

- **Auto-Detection**: Automatically finds VRChat log files
- **Message Filtering**: Ignore system messages, joins/leaves, or specific users
- **User Blacklist/Whitelist**: Control which users' messages are spoken
- **Debug Diagnostics**: Test connection, view log files, see parsing details
- **Real-time Status**: Message counter and hover tooltip with statistics

### Testing & Diagnostics

Use the built-in diagnostic tools:
- **Test Connection**: Verifies log file access and shows recent chat messages
- **View Log File**: Displays last 20 lines with parsing indicators
- **Debug Mode**: Enable verbose logging to console for troubleshooting

For detailed setup instructions, troubleshooting, and FAQs, see [docs/VRCHAT_INTEGRATION.md](docs/VRCHAT_INTEGRATION.md).

### VRChat OSC Chatbox and Notification Sound

CriTTS can send TTS output to VRChat's in-game chatbox via OSC (e.g. when "Send to chatbox when speaking" is enabled in Settings > VRChat OSC).

- **Notification sound**: The "Play notification sound when sending" option uses VRChat's built-in chatbox notification sound. It is controlled by VRChat, not a custom sound file.
- **Requirements**: VRChat must have OSC enabled in its settings. The notification sound may not work in all VRChat versions.
- **If notification sound doesn't work**: Ensure OSC is enabled in VRChat, that you are using a supported VRChat version, and try toggling the setting off and on. Behavior can vary by VRChat build.

## Installation


### Prerequisites

- Python 3.8 or higher
- Windows, macOS, or Linux

### Install Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:

```bash
pip install customtkinter edge-tts>=7.2.3 sounddevice soundfile numpy Pillow
```

### VB-Cable Setup (for Discord Integration)

To use CriTTS Recoded with Discord or other applications:

1. **Download VB-Cable**:
   - Visit [VB-Audio Software](https://vb-audio.com/Cable/)
   - Download and install VB-Cable (free version available)

2. **Set Up Discord**:
   - Open Discord settings
   - Go to Voice & Video
   - Set Input Device to "CABLE Output (VB-Audio Virtual Cable)"
   - Disable "Automatically determine input sensitivity"
   - Set input sensitivity to minimum (-100dB)

3. **Configure CriTTS Recoded**:
   - Open CriTTS Recoded
   - Click "Settings"
   - Go to "Audio Output" tab
   - Select "CABLE Input (VB-Audio Virtual Cable)" as output device
   - Save settings

4. **Usage**:
   - Type text in CriTTS Recoded
   - Click "Speak" or press Ctrl+Enter
   - Audio will be routed to Discord automatically

## Usage

### Running the Application

```bash
python main.py
```

### Basic Usage

1. **Enter Text**: Type or paste text in the main text area
2. **Speak**: Click the "Speak" button or press Ctrl+Enter
3. **Stop**: Click "Stop" or press Escape to stop playback
4. **Clear**: Click "Clear" or press Ctrl+T to clear text

### Changing Settings

1. Click "Settings" button
2. **Voice Tab**: Select voice, adjust rate, volume, and pitch
3. **Audio Output Tab**: Select output device (e.g., VB-Cable)
4. **Appearance Tab**: Switch between Dark/Light/System mode
5. Click "Save" to apply changes

### Voice Search and Filters

In the Voice settings tab, use the search box and filter dropdowns to find voices:

- **Search box**: Find voices by name (e.g., "Aria", "Guy"), locale (e.g., "en-US", "es-ES"), or language code.
- **Language filter**: Dropdown is populated from loaded voices (e.g., "All Languages", "en", "es", "fr", "ja"). Select a language to show only voices for that language.
- **Region filter**: Dropdown lists locales from loaded voices (e.g., "All Regions", "en-US", "en-GB", "es-ES"). Select a region to narrow by locale.
- **Gender filter**: Choose "All", "Male", or "Female".

Filters are applied together. Use **Clear** to reset all filters to "All" / "All Languages" / "All Regions".

## Project Structure

```
TTS - copia/
├── image.ico              # Application icon
├── main.py               # Application entry point
├── requirements.txt      # Python dependencies
├── README.md            # This file
└── src/
    ├── __init__.py
    ├── config/
    │   ├── __init__.py
    │   └── settings_manager.py    # JSON settings persistence
    ├── tts/
    │   ├── __init__.py
    │   └── tts_engine.py          # edge_tts integration
    ├── audio/
    │   ├── __init__.py
    │   └── audio_router.py        # sounddevice audio routing
    └── gui/
        ├── __init__.py
        ├── main_window.py         # Main application window
        └── settings_window.py     # Settings dialog
```

## Troubleshooting

### No Audio Output

1. Check that the correct output device is selected in Settings > Audio Output
2. Ensure the selected device is not muted in Windows Sound settings
3. Try "System Default" device to use your main speakers

### VB-Cable Not Working with Discord

1. Verify VB-Cable is installed correctly
2. Check Discord input device is set to "CABLE Output"
3. Disable noise suppression and echo cancellation in Discord
4. Run both CriTTS Recoded and Discord as administrator (if needed)

### TTS Not Working / No Voices Load

1. Check internet connection (edge_tts requires internet)
2. Verify firewall is not blocking Python/edge_tts
3. Try refreshing voices in Settings (click Refresh button)

### Application Won't Start

1. Ensure all dependencies are installed: `pip install -r requirements.txt`
2. Check Python version: `python --version` (must be 3.8+)
3. Try running from command line to see error messages: `python main.py`

### VRChat Messages Not Detected

1. **Check VRChat is running** - Logs are only written while VRChat is active
2. **Verify log path** - Use "Test Connection" in Settings > VR Mode
3. **Check for chat activity** - Someone needs to send a message for detection
4. **Enable debug mode** - Check "Log all lines" to see what's being read
5. **View log file** - Use "View Log File" to see recent entries and parsing results

**Note:** Your own messages typed in VRChat will NOT be detected (VRChat limitation). Only messages from other players are logged.

### Audio Quality Issues


1. Open Settings and go to the "Audio Quality" tab
2. Select a higher quality preset: "High (192kbps)" or "Maximum (Lossless)"
3. Enable audio normalization for consistent volume
4. Try different voices - some have better quality than others
5. Adjust speech rate - very fast/slow rates may affect clarity

**Quality Presets:**
- **Maximum (Lossless)**: Best quality, uses more memory. Good for short texts.
- **High (192kbps)**: Recommended for most use cases. Excellent quality with reasonable file size.
- **Medium (96kbps)**: Good balance between quality and performance.
- **Low (48kbps)**: Smaller files, lower quality. Useful for slow connections.


## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Enter | Speak text |
| Escape | Stop playback |
| Ctrl+T | Clear text |
| Ctrl+Shift+V | Toggle VR Mode |
| Ctrl+, | Open Settings |

## Performance Optimizations

CriTTS Recoded includes several performance optimizations for faster TTS generation:

### Audio Cache

- **Persistent Disk Cache**: Generated audio is cached to disk, so identical text won't need regeneration
- **LRU Eviction**: Oldest cached items are removed when cache size limit is reached
- **Configurable Size**: Adjust cache size in Settings (default: 500MB)
- **Cache Statistics**: View hits, misses, and saved time in Settings

### Phrase Pre-generation

- **Usage Tracking**: Commonly used phrases are tracked automatically
- **Pre-generation**: Frequently used phrases can be pre-generated for instant playback
- **Configurable Thresholds**: Set minimum uses and maximum phrases to pre-generate

### Text Processing Cache

- **Preprocessing Cache**: Text preprocessing results are cached for faster repeated generation
- **Configurable Size**: Adjust text cache size in Settings

## VRChat Lip-Sync Integration

CriTTS Recoded can animate your VRChat avatar's mouth to match TTS output:

### Viseme Animation

- **Automatic Lip-Sync**: Avatar mouth moves in sync with generated speech
- **Rule-Based Phoneme Detection**: Text is analyzed to determine mouth shapes
- **15 VRChat Visemes**: Full support for all VRChat viseme values

### Voice Amplitude

- **Real-Time Amplitude**: Avatar mouth opens based on audio volume
- **Smooth Transitions**: Amplitude values are smoothed for natural movement

### Setup

1. Enable VRChat OSC in Settings > VRChat OSC
2. Enable "Viseme Animation" for lip-sync
3. Enable "Voice Amplitude" for volume-based mouth movement
4. Ensure VRChat has OSC enabled in its settings

### Requirements

- VRChat must have OSC enabled (Settings > OSC > Enable OSC)
- Avatar must support Viseme and Voice parameters
- Works with most avatars that have lip-sync support

## Quality Presets

CriTTS Recoded supports quality presets for different use cases:

| Preset | Description | Best For |
|--------|-------------|----------|
| **Fast Preview** | Quick generation, lower quality | Testing, quick previews |
| **Balanced** | Good quality with reasonable speed | General use, recommended |
| **High Quality** | Maximum quality, slower generation | Important content, recordings |

Configure presets in Settings > Behavior > Quality Preset.

## Credits

- **GUI Framework**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) by Tom Schimansky
- **TTS Engine**: [edge-tts](https://github.com/rany2/edge-tts) by rany2
- **Audio Routing**: [sounddevice](https://python-sounddevice.readthedocs.io/) and [soundfile](https://pysoundfile.readthedocs.io/)
- **VB-Cable**: [VB-Audio Software](https://vb-audio.com/Cable/)

## License

This project is open source. Feel free to modify and distribute according to your needs.

## Support

For issues, questions, or contributions, please refer to the project repository or contact the developer.

---

**Enjoy CriTTS Recoded!** 🎙️
