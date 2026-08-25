"""Linux PulseAudio/PipeWire null-sink and virtual-mic management.

Extracted from ``AudioRouter`` so sink lifecycle (create/ensure/cleanup),
stream routing, and audio-server detection live in one focused class.
``AudioRouter`` keeps thin delegating shims with the original names, so all
existing callers (main.py, settings tabs, tests) keep working unchanged.
"""
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class LinuxSinkManager:
    """Manages the CriTTS null sink + virtual mic on PulseAudio/PipeWire."""

    def __init__(self):
        # Sink name to auto-route TTS audio to (set externally before playback)
        self._sink_name: str = ""

        # Lazy-cached Linux audio system detection
        self._cached_audio_system: Optional[str] = None

        # Last startup auto-setup result, surfaced later in the Audio Output
        # settings tab.  ``(ok, message)`` or ``None`` when it hasn't run yet.
        self.last_result: Optional[Tuple[bool, str]] = None

    @property
    def is_linux(self) -> bool:
        """Return True if running on Linux."""
        return sys.platform.startswith("linux")

    def set_sink_name(self, name: str) -> None:
        """Set the PulseAudio sink name to auto-route TTS audio to (Linux only)."""
        self._sink_name = (name or "").strip()

    @staticmethod
    def cleanup_modules() -> None:
        """Unload any PulseAudio/PipeWire modules created by CriTTS (idempotent).

        Scans ``pactl list short modules`` for entries containing our marker
        strings and unloads them by module ID.  Safe to call even if no
        modules exist — does nothing and never raises.
        """
        if not sys.platform.startswith("linux"):
            return
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "modules"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            return

        for line in result.stdout.splitlines():
            # Look for modules we created: CriTTS_Null_Sink / CriTTS_Virtual_Mic
            if "CriTTS_Null_Sink" not in line and "CriTTS_Virtual_Mic" not in line:
                continue
            module_id = line.split("\t", 1)[0].strip()
            if not module_id.isdigit():
                continue
            try:
                subprocess.run(
                    ["pactl", "unload-module", module_id],
                    capture_output=True, timeout=3,
                )
                logger.debug("Unloaded PulseAudio module %s", module_id)
            except Exception:
                logger.debug("PulseAudio module unload failed", exc_info=True)

    @staticmethod
    def ensure_modules(sink_name: str = "crittssink") -> tuple:
        """Idempotently create the CriTTS null sink + virtual mic (Linux only).

        ``pactl load-module`` entries are ephemeral — they vanish when the
        audio server restarts and are removed on app exit — so startup re-runs
        this to restore routing for users who have already opted in.  Safe to
        call when the modules already exist (no-op).  Returns ``(ok, message)``
        where ``ok`` is False only for fatal failures; ``message`` is
        human-readable status for logging or the settings UI.
        """
        if not sys.platform.startswith("linux"):
            return True, ""

        if not shutil.which("pactl"):
            return False, "⚠ pactl not found. Is PipeWire installed?"

        # 1. Check / create the null sink (fixed description so cleanup finds it)
        sink_description = "CriTTS_Null_Sink"
        try:
            check = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True, text=True, timeout=5,
            )
        except subprocess.TimeoutExpired:
            return False, "⚠ pactl timed out. Check your audio system."
        except FileNotFoundError:
            return False, "⚠ pactl not found. Is PipeWire installed?"
        except Exception as e:
            return False, f"❌ Unexpected error: {e}"

        sink_exists = any(
            sink_name.lower() == part.strip().lower()
            for line in check.stdout.splitlines()
            for part in line.split("\t")
        )
        if not sink_exists:
            try:
                created = subprocess.run(
                    ["pactl", "load-module", "module-null-sink",
                     f"sink_name={sink_name}",
                     f"sink_properties=device.description={sink_description}"],
                    capture_output=True, text=True, timeout=10,
                )
            except subprocess.TimeoutExpired:
                return False, "⚠ pactl timed out. Check your audio system."
            except Exception as e:
                return False, f"❌ Unexpected error: {e}"
            if created.returncode != 0:
                err = created.stderr.strip() or "Unknown error"
                return False, f"❌ Failed to create sink: {err}"

        # 2. Check / create the virtual mic from the sink monitor
        virtual_mic_description = "CriTTS_Virtual_Mic"
        virtual_mic_name = f"{sink_name}_mic"
        try:
            sources_check = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, text=True, timeout=5,
            )
        except subprocess.TimeoutExpired:
            return False, "⚠ pactl timed out. Check your audio system."
        except Exception as e:
            return False, f"❌ Unexpected error: {e}"

        mic_exists = any(
            virtual_mic_name in line.split("\t")
            or virtual_mic_description in line.split("\t")
            for line in sources_check.stdout.splitlines()
        )
        if not mic_exists:
            try:
                mic_created = subprocess.run(
                    ["pactl", "load-module", "module-remap-source",
                     f"source_name={virtual_mic_name}",
                     f"source_properties=device.description={virtual_mic_description}",
                     f"master={sink_name}.monitor"],
                    capture_output=True, text=True, timeout=10,
                )
            except subprocess.TimeoutExpired:
                return False, "⚠ pactl timed out. Check your audio system."
            except Exception as e:
                return False, f"❌ Unexpected error: {e}"
            if mic_created.returncode != 0:
                err = mic_created.stderr.strip() or "Unknown error"
                return True, (
                    "✅ Null sink ready.\n"
                    f"⚠ Virtual mic failed ({err}).\n"
                    f"   Check: pactl list sources short | grep {sink_name}"
                )

        return True, f"✅ Ready! Set Discord input to:\n   {virtual_mic_description}"

    def route_to_sink(self) -> None:
        """Spawn a daemon thread that polls for the just-created sink input
        and moves it to the configured PulseAudio/PipeWire sink.

        Uses ``pactl list sink-inputs`` (one call per poll) and matches our
        stream by either process ID (PulseAudio-native clients) or application
        name (ALSA clients, which lack a PID field on PipeWire).
        Polls every 80 ms with a 3 s deadline.
        """
        if not self.is_linux or not self._sink_name:
            return
        sink_name = self._sink_name

        # Match tokens: PID for PulseAudio-native, app name for ALSA.
        pid_token = f'application.process.id = "{os.getpid()}"'
        try:
            py_exe = os.path.basename(os.path.realpath(sys.executable))
        except OSError:
            py_exe = os.path.basename(sys.executable)
        alsa_token = f'PipeWire ALSA [{py_exe}]'

        def _route():
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                time.sleep(0.08)
                try:
                    result = subprocess.run(
                        ["pactl", "list", "sink-inputs"],
                        capture_output=True, text=True, timeout=3,
                    )
                except Exception:
                    continue

                blocks = result.stdout.split("Sink Input #")
                for block in blocks[1:]:
                    # Skip blocks not belonging to our process
                    if pid_token not in block and alsa_token not in block:
                        continue
                    first_line = block.split("\n", 1)[0]
                    sink_input_id = first_line.strip().split()[0]
                    if not sink_input_id.isdigit():
                        continue
                    try:
                        subprocess.run(
                            ["pactl", "move-sink-input", sink_input_id, sink_name],
                            capture_output=True, timeout=3,
                        )
                        logger.debug(
                            "Routed sink-input %s to sink '%s'",
                            sink_input_id, sink_name,
                        )
                    except Exception:
                        logger.debug("Sink-input routing failed", exc_info=True)
                    return  # routed successfully — stop polling

        threading.Thread(target=_route, daemon=True).start()

    def detect_audio_system(self) -> str:
        """
        Detect which audio system is running on Linux.

        The result is cached after the first call to avoid repeated
        subprocess invocations during GUI rendering.

        Returns:
            One of 'pipewire', 'pulseaudio', or 'unknown'.
        """
        if self._cached_audio_system is not None:
            return self._cached_audio_system

        if not sys.platform.startswith("linux"):
            self._cached_audio_system = "unknown"
            return "unknown"

        detected = "unknown"
        try:
            pactl = shutil.which("pactl")
            if pactl:
                result = subprocess.run(
                    [pactl, "info"], capture_output=True, text=True, timeout=3
                )
                server = result.stdout
                if "PipeWire" in server:
                    detected = "pipewire"
                elif "PulseAudio" in server or "pulseaudio" in server.lower():
                    detected = "pulseaudio"
        except Exception:
            logger.debug("Audio server detection failed", exc_info=True)

        if detected == "unknown":
            # Check for PipeWire via pw-cli as fallback
            try:
                if shutil.which("pw-cli"):
                    result = subprocess.run(
                        ["pw-cli", "info", "0"], capture_output=True, text=True, timeout=3
                    )
                    if result.returncode == 0:
                        detected = "pipewire"
            except Exception:
                logger.debug("PipeWire probe via pactl failed", exc_info=True)

        self._cached_audio_system = detected
        return detected
