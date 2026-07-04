### This is a personal project made for fun :)

# CriTTS Recoded

A modern, free Text-to-Speech (TTS) application with a sleek GUI. CriTTS supports both **online** and **offline** TTS — it integrates Microsoft Edge's TTS engine (via edge-tts) for high-quality online speech, Piper TTS for fast local synthesis, and Coqui XTTS v2 for higher-quality offline speech. Audio can be routed to any output device, including virtual cables for Discord/VRChat integration.

## Features

### Core TTS
- **Free Online TTS Engine**: Uses Microsoft Edge's online TTS service (no API key required)
- **Offline TTS Engines**: Choose [Piper TTS](https://github.com/rhasspy/piper) for fast local playback or Coqui XTTS v2 for higher-quality offline synthesis
- **100+ Voices**: Access to all Microsoft Edge voices plus curated Piper and Coqui offline voices
- **Voice Customization**: Adjust speech rate (-100 to +100), volume (0-100), and pitch (-100 to +100)
- **Auto Language Detection**: Automatically detects text language and selects appropriate voice
- **Custom Language Mappings**: Set preferred voices for each language

### Audio Processing
- **Audio Routing**: Route TTS output to any audio device (including VB-Cable for Discord)
- **Microphone Passthrough**: Route your real microphone to VB-Cable alongside TTS for voice mixing
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
- **Recording Overlay**: Compact always-on-top overlay showing recording state with pulsing indicator (draggable, toggleable)

### Voice Input (STT)
- **Speech-to-Text**: Record microphone audio and transcribe using Google Web Speech API
- **Auto-Speak**: Optionally speak transcribed text automatically
- **Language Support**: Configure recognition language in Settings → Behavior

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
```

**Using launcher scripts (recommended):**

```bash
# Windows
run.bat

# Linux / macOS
./run.sh
```

The launcher scripts are zero-step on fresh installs:

1. **Auto-detect / auto-install Python** — if `python` (and `py -3` on Windows) isn't on PATH, the launcher prompts you once and offers to install Python for you:
   - On Windows: downloads the python.org installer silently (per-user, with pip and PATH), or bootstraps via uv.
   - On Linux/macOS: uses the system package manager (`apt`, `dnf`, `pacman`, or Homebrew), or falls back to uv.
2. **Install Python dependencies** against `requirements.txt` via `scripts/install_deps.py`, which already cascades through `pip` → `pip.exe` → `uv` → `ensurepip` to handle Microsoft Store Python, pip-less venvs, and other oddities.
3. **Launch** `main.py`.

The launcher caches a fingerprint of `requirements.txt` so subsequent runs only re-install when dependencies change.

**Manual installation:**

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Dependencies

```
customtkinter
edge-tts>=7.2.3
piper-tts>=1.2.0
coqui-tts[codec]>=0.27.5
langid>=1.1.6
sounddevice
soundfile>=0.12.0
numpy>=1.21.0
scipy>=1.9.0
pyloudnorm>=0.1.0
python-osc>=1.8.0
SpeechRecognition
keyboard>=0.13.5
```

## Usage

### Basic Operation

1. **Enter Text**: Type or paste text in the main text area
2. **Speak**: Click "Speak" or press `Enter`
3. **Stop**: Click "Stop" or press `Escape`
4. **Clear**: Click "Clear" or press `Ctrl+T`

### Voice Input

Click the **🎙 Voice** button (or press `Ctrl+Shift+V`) to start recording. Click again (or press the keybind again) to stop and transcribe.

- Uses Google Web Speech API (free, requires internet)
- Configure language and microphone in **Settings → Behavior**
- Enable **Auto-Speak** to automatically speak transcribed text

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
- **Microphone Passthrough**: Route your real microphone to VB-Cable alongside TTS
  - Enable/disable passthrough
  - Select microphone device
  - Adjust passthrough volume (0-200%)

#### Appearance Tab
- Switch between Dark, Light, or System theme
- **Button Visibility**: Choose which buttons appear in the main window (Speak, Stop, Clear, Voice, Overlay). Settings button is always visible.

#### Abbreviations Tab
- Define text expansion shortcuts (e.g., "idk" → "I don't know")

#### Keybinds Tab
- Customize all keyboard shortcuts

#### Behavior Tab
- Configure speak mode (current line or all text)
- Enable auto language detection
- Set language-to-voice mappings

#### Soundboard Tab
- Map soundboard slots to local audio files
- Enable or disable inline soundboard command parsing for tokens like `[1]`

#### VRChat OSC Tab
- Enable OSC integration
- Configure chatbox settings
- Set up viseme/amplitude for lip-sync

#### Advanced Tab
- Manage audio cache settings
- Select processing profile
- Enable streaming playback (experimental)

#### TTS Provider Tab
- Switch between **Edge TTS (Online)**, **Piper TTS (Offline Fast)**, and **Coqui TTS (Offline High Quality)**
- Review provider-specific capabilities before saving
- Configure Coqui GPU selection and speech language when using Coqui TTS

## Offline TTS Providers

CriTTS includes built-in support for both offline providers:

- [Piper TTS](https://github.com/rhasspy/piper) for fast, local neural text-to-speech with per-voice model downloads.
- Coqui XTTS v2 for higher-quality offline synthesis with a larger first-use model download.

### Switching Offline Providers

1. Open **Settings → TTS Provider**
2. Change **Active Provider** to **Piper TTS (Offline Fast)** or **Coqui TTS (Offline High Quality)**
3. Choose a voice from the selected provider's voice list

### First-Use Model Download

Piper voice models are downloaded automatically the first time they are used and cached in `~/.critts/piper_voices/`. Model files range from a few MB (x-low quality) to ~100 MB (high quality).

Coqui XTTS v2 downloads a larger shared model on first use (about 1.8 GB) and then runs fully offline.

While a model is downloading or loading, the **status bar** at the bottom of the main window shows a live indicator. Subsequent uses of the same model are instant.

### Available Piper Voices

| Voice | Locale | Gender | Quality |
|-------|--------|--------|---------|
| English (US) – Lessac | en-US | Male | Medium |
| English (US) – Ryan | en-US | Male | High |
| English (US) – Amy | en-US | Female | Low |
| English (US) – Ljspeech | en-US | Female | High |
| English (GB) – Alan | en-GB | Male | Medium |
| English (GB) – Jenny Dioco | en-GB | Female | Medium |
| German – Thorsten | de-DE | Male | Medium |
| Spanish (ES) – Carlfm | es-ES | Male | x-low |
| Spanish (MX) – Claude | es-MX | Male | High |
| French – Siwis | fr-FR | Female | Medium |
| Italian – Riccardo | it-IT | Male | x-low |
| Portuguese (BR) – Faber | pt-BR | Male | Medium |
| Russian – Ruslan | ru-RU | Male | Medium |
| Dutch – Mls | nl-NL | Female | Medium |
| Polish – Mls 6892 | pl-PL | Female | Low |
| Ukrainian – Lada | uk-UA | Female | x-low |
| Vietnamese – Vivos | vi-VN | Female | x-low |
| Turkish – Dfki | tr-TR | Male | Medium |
| Romanian – Mihai | ro-RO | Male | Medium |

> **Note**: Piper does not support pitch adjustment. Rate and volume controls work normally.

## VB-Cable Setup (Discord Integration)

To route TTS audio to Discord or other applications:

1. **Install VB-Cable**
   - Download from [VB-Audio Software](https://vb-audio.com/Cable/)
   - Install the virtual audio cable
   - CriTTS will automatically detect if VB-Cable is missing and prompt you to install it

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

## Microphone Passthrough

The Microphone Passthrough feature allows you to route your real microphone audio to VB-Cable alongside TTS output. This is useful for mixing your voice with TTS in VRChat or Discord.

### Setup

1. **Enable Passthrough**
   - Open Settings > Audio Output
   - Scroll to "Microphone Passthrough" section
   - Check "Enable microphone passthrough to VBCable"

2. **Select Microphone**
   - Choose your microphone device from the dropdown
   - Use "Default (System)" to use your system's default microphone

3. **Adjust Volume**
   - Set passthrough volume (0-200%)
   - 100% = normal volume
   - 200% = doubled volume (for quiet microphones)
   - 0% = muted

### Use Cases

- **VRChat**: Speak normally while TTS plays, both audio sources go to VB-Cable
- **Discord**: Mix your voice with TTS for roleplay or accessibility
- **Streaming**: Combine voice and TTS into a single audio source

### How It Works

When enabled, CriTTS creates a real-time audio stream from your selected microphone to VB-Cable. This runs continuously in the background, allowing you to speak naturally while TTS plays. The volume control lets you boost quiet microphones or balance levels between your voice and TTS.

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
    │       ├── edge_tts_provider.py   # edge-tts integration (online)
    │       └── piper_tts_provider.py  # Piper TTS integration (offline)
    ├── audio/
    │   └── audio_router.py        # Audio device routing & processing
    ├── stt/
    │   └── stt_engine.py          # Speech-to-text engine
    ├── utils/
    │   ├── language_detector.py   # Language detection for auto voice selection
    │   └── keybind_utils.py       # Keybind utility functions
    ├── gui/
    │   ├── main_window.py         # Main application window
    │   ├── settings_window.py     # Settings dialog
    │   ├── keybind_manager.py     # Dynamic keybind registration
    │   ├── theme_constants.py     # UI theme & layout constants
    │   ├── recording_overlay.py   # Recording state overlay
    │   └── settings_tabs/         # Settings tab components
    │       ├── voice_tab.py           # Voice selection & customization
    │       ├── audio_output_tab.py    # Audio device & normalization
    │       ├── appearance_tab.py      # Theme & button visibility
    │       ├── abbreviations_tab.py   # Text expansion shortcuts
    │       ├── keybinds_tab.py        # Keyboard shortcuts
    │       ├── behavior_tab.py        # Speak mode & language detection
    │       ├── vrchat_osc_tab.py      # VRChat OSC integration
    │       └── advanced_tab.py        # Cache & processing profiles
    └── vrchat/
        ├── osc_client.py          # VRChat OSC client
        └── viseme_mapper.py       # Phoneme-to-viseme mapping
```

## Keyboard Shortcuts

| Default Shortcut | Action |
|------------------|--------|
| `Escape` | Stop playback |
| `Ctrl+T` | Clear text |
| `Ctrl+,` | Open Settings |
| `Ctrl+Shift+V` | Voice input (toggle recording) |

All shortcuts are customizable in Settings > Keybinds.

**Global Hotkeys**: Enable the "Global Hotkeys" toggle in Settings > Keybinds to allow shortcuts to work even when the app is not focused. This requires the `keyboard` library (included in dependencies).

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

### Piper Model Download Stuck / Failed
1. Ensure you have an internet connection for the **first** use of a Piper voice (models are downloaded once from Hugging Face and cached locally)
2. The status bar shows download progress — wait for "Loading Piper model…" to complete before speaking
3. Cached models are stored in `~/.critts/piper_voices/` — delete the folder to force a fresh download

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

