### This is a personal project made for fun :)

# CriTTS Recoded

A modern, free Text-to-Speech (TTS) application with a sleek GUI. CriTTS uses Microsoft Edge's TTS engine (via edge-tts) to generate high-quality speech and can route audio to any output device, including virtual cables for Discord/VRChat integration.

## Features

### Core TTS
- **Free TTS Engine**: Uses Microsoft Edge's online TTS service (no API key required)
- **100+ Voices**: Access to all Microsoft Edge voices in multiple languages
- **Voice Customization**: Adjust speech rate (-100 to +100), volume (0-100), and pitch (-100 to +100)
- **Auto Language Detection**: Automatically detects text language and selects appropriate voice
- **Custom Language Mappings**: Set preferred voices for each language

### Audio Processing
- **Audio Routing**: Route TTS output to any audio device (including VB-Cable for Discord)
- **Processing Profiles**: Choose between Fast Preview, Balanced, or High Quality
- **Audio Normalization**: Peak, RMS, or LUFS normalization for consistent volume
- **High-Quality Resampling**: 48kHz with Kaiser-windowed anti-aliasing filters
- **Stereo Enhancement**: Converts mono TTS to natural-sounding stereo

### Performance
- **Persistent Audio Cache**: Generated audio is cached to disk for instant replay
- **LRU Cache Eviction**: Configurable cache size with automatic cleanup
- **Phrase Pre-generation**: Frequently used phrases can be pre-generated
- **Streaming Playback**: Experimental low-latency mode starts playing before generation completes

### GUI
- **Modern Interface**: Built with CustomTkinter for a sleek, modern look
- **Dark/Light Mode**: Switch between themes or follow system setting
- **Voice Search & Filters**: Search by name, filter by language/region/gender
- **Voice Favorites**: Save favorite voices for quick access
- **Configurable Keybinds**: All keyboard shortcuts are customizable

### VRChat Integration
- **OSC Chatbox**: Send TTS text to VRChat's in-game chatbox
- **Viseme Animation**: Automatic lip-sync for your avatar
- **Voice Amplitude**: Real-time mouth movement based on audio volume
- **Typing Indicator**: Show typing animation in VRChat while composing

## Installation

### Prerequisites
- Python 3.8 or higher
- Windows, macOS, or Linux

### Quick Start

```bash
# Clone the repository
git clone https://github.com/k1rk11/CriTTS.git
cd CriTTS

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Dependencies

```
customtkinter
edge-tts>=7.2.3
sounddevice
soundfile>=0.12.0
numpy>=1.21.0
scipy>=1.9.0
pyloudnorm>=0.1.0
Pillow
watchdog>=3.0.0
python-osc>=1.8.0
```

## Usage

### Basic Operation

1. **Enter Text**: Type or paste text in the main text area
2. **Speak**: Click "Speak" or press `Enter`
3. **Stop**: Click "Stop" or press `Escape`
4. **Clear**: Click "Clear" or press `Ctrl+T`

### Settings

Access settings by clicking the "Settings" button or pressing `Ctrl+,`

#### Voice Tab
- Select voice from the list (100+ voices available)
- Adjust rate, volume, and pitch
- Preview voices before selecting
- Manage favorite voices

#### Audio Output Tab
- Select output device
- Enable/disable normalization
- Choose normalization type (Peak, RMS, LUFS)

#### Appearance Tab
- Switch between Dark, Light, or System theme

#### Abbreviations Tab
- Define text expansion shortcuts (e.g., "idk" → "I don't know")

#### Keybinds Tab
- Customize all keyboard shortcuts

#### Behavior Tab
- Configure speak mode (current line or all text)
- Enable auto language detection
- Set language-to-voice mappings

#### VRChat OSC Tab
- Enable OSC integration
- Configure chatbox settings
- Set up viseme/amplitude for lip-sync

#### Advanced Tab
- Manage audio cache settings
- Select processing profile
- Enable streaming playback (experimental)

## VB-Cable Setup (Discord Integration)

To route TTS audio to Discord or other applications:

1. **Install VB-Cable**
   - Download from [VB-Audio Software](https://vb-audio.com/Cable/)
   - Install the virtual audio cable

2. **Configure CriTTS**
   - Open Settings > Audio Output
   - Select "CABLE Input (VB-Audio Virtual Cable)"

3. **Configure Discord**
   - Open Discord Settings > Voice & Video
   - Set Input Device to "CABLE Output"
   - Disable "Automatically determine input sensitivity"

4. **Use**
   - Type text in CriTTS and click Speak
   - Audio will be routed to Discord

## Audio Processing Profiles

| Profile | Sample Rate | Anti-Aliasing | Stereo Width | Best For |
|---------|-------------|---------------|--------------|----------|
| Fast Preview | Original | None | None | Quick testing |
| Balanced | 48kHz | Kaiser β=5 | 0.3 | General use (default) |
| High Quality | 48kHz | Kaiser β=8 | 0.5 | Important content |

## Normalization Types

| Type | Description | Best For |
|------|-------------|----------|
| **Peak** | Limits maximum amplitude to -1dB | General use, prevents clipping |
| **RMS** | Ensures consistent loudness | Multi-voice projects |
| **LUFS** | Professional loudness standards (-14 LUFS) | Streaming, broadcast |
| **None** | No processing | External audio workflows |

## VRChat Integration

### Setup

1. Enable VRChat OSC in Settings > VRChat OSC
2. Ensure OSC is enabled in VRChat (Settings > OSC > Enable OSC)
3. Configure desired features:
   - **Send to Chatbox**: Display TTS text in VRChat
   - **Viseme Animation**: Animate avatar mouth
   - **Voice Amplitude**: Real-time mouth movement

### Features

- **Chatbox Integration**: TTS text appears in VRChat's chatbox
- **Lip-Sync**: Avatar mouth moves in sync with speech
- **Typing Indicator**: Shows typing animation while composing

### Limitations

- Only incoming messages from other players can be monitored (VRChat limitation)
- Your own typed messages in VRChat are not logged by VRChat

## Project Structure

```
CriTTS/
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
├── README.md                  # This file
└── src/
    ├── config/
    │   └── settings_manager.py    # JSON settings persistence
    ├── tts/
    │   ├── tts_engine.py          # TTS orchestration
    │   ├── text_preprocessor.py   # Text cleaning & abbreviation expansion
    │   ├── audio_cache.py         # Persistent LRU audio cache
    │   └── providers/
    │       └── edge_tts_provider.py   # edge-tts integration
    ├── audio/
    │   └── audio_router.py        # Audio device routing & processing
    ├── gui/
    │   ├── main_window.py         # Main application window
    │   ├── settings_window.py     # Settings dialog
    │   ├── keybind_manager.py     # Dynamic keybind registration
    │   └── theme_constants.py     # UI theme & layout constants
    └── vrchat/
        ├── osc_client.py          # VRChat OSC client
        └── viseme_mapper.py       # Phoneme-to-viseme mapping
```

## Keyboard Shortcuts

| Default Shortcut | Action |
|------------------|--------|
| `Ctrl+Enter` | Speak text |
| `Escape` | Stop playback |
| `Ctrl+T` | Clear text |
| `Ctrl+,` | Open Settings |

All shortcuts are customizable in Settings > Keybinds.

## Troubleshooting

### No Audio Output
1. Check output device in Settings > Audio Output
2. Ensure device is not muted in system settings
3. Try "System Default" device

### VB-Cable Not Working
1. Verify VB-Cable is installed correctly
2. Check Discord input device is "CABLE Output"
3. Disable noise suppression in Discord

### TTS Not Working
1. Check internet connection (edge-tts requires internet)
2. Verify firewall is not blocking Python
3. Try refreshing voices in Settings

### VRChat Integration Issues
1. Ensure OSC is enabled in VRChat settings
2. Check IP/port configuration (default: 127.0.0.1:9000)
3. Use "Test Connection" in Settings > VRChat OSC

## Performance Tips

1. **Enable Audio Cache**: Reduces regeneration of repeated phrases
2. **Use Balanced Profile**: Good quality without excessive processing
3. **Pre-generate Phrases**: Common phrases load instantly
4. **Enable Streaming**: Lower latency for long text (experimental)

## Credits

- **GUI Framework**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- **TTS Engine**: [edge-tts](https://github.com/rany2/edge-tts)
- **Audio I/O**: [sounddevice](https://python-sounddevice.readthedocs.io/), [soundfile](https://pysoundfile.readthedocs.io/)
- **Virtual Audio**: [VB-Audio Cable](https://vb-audio.com/Cable/)

## License

This project is open source. Feel free to modify and distribute.

---


**Enjoy CriTTS Recoded!** 🎙️

