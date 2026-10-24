"""Linux PulseAudio/PipeWire null-sink and virtual-mic management.

Extracted from ``AudioRouter`` so sink lifecycle (create/ensure/cleanup),
stream routing, and audio-server detection live in one focused class.
``AudioRouter`` keeps thin delegating shims with the original names, so all
existing callers (main.py, settings tabs, tests) keep working unchanged.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class LinuxSinkManager:
    """Manages the CriTTS null sink + virtual mic on PulseAudio/PipeWire."""

    # Upper bounds for the stream-open handshake (see begin_stream_open).
    _OPEN_LOCK_TIMEOUT = 2.0  # wait for another stream's handshake
    _IDENTIFY_TIMEOUT = 1.0  # wait for our sink input to appear while holding the lock
    _ROUTE_TIMEOUT = 4.0  # keep retrying the move this long after start

    def __init__(self):
        # Serialises stream opens of this process; see begin_stream_open.
        self._open_lock = threading.Lock()
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
                capture_output=True,
                text=True,
                timeout=5,
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
                    capture_output=True,
                    timeout=3,
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
            return False, "⚠ pactl is missing. Install the PulseAudio utilities package, then retry."

        # 1. Check / create the null sink (fixed description so cleanup finds it)
        sink_description = "CriTTS_Null_Sink"
        try:
            check = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return False, "⚠ Audio server did not respond. Restart PipeWire/PulseAudio, then retry."
        except FileNotFoundError:
            return False, "⚠ pactl is missing. Install the PulseAudio utilities package, then retry."
        except Exception as e:
            return False, f"❌ Could not check audio sinks: {e}"
        if check.returncode != 0:
            err = check.stderr.strip() or "pactl could not connect"
            return False, (
                f"⚠ Cannot contact the audio server: {err}. "
                "Start PipeWire/PulseAudio, then retry."
            )

        sink_exists = any(
            sink_name.lower() == part.strip().lower() for line in check.stdout.splitlines() for part in line.split("\t")
        )
        if not sink_exists:
            try:
                created = subprocess.run(
                    [
                        "pactl",
                        "load-module",
                        "module-null-sink",
                        f"sink_name={sink_name}",
                        f"sink_properties=device.description={sink_description}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
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
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return False, "⚠ Audio server did not respond. Restart PipeWire/PulseAudio, then retry."
        except Exception as e:
            return False, f"❌ Could not check audio sources: {e}"
        if sources_check.returncode != 0:
            err = sources_check.stderr.strip() or "pactl could not connect"
            return False, (
                f"⚠ Cannot contact the audio server: {err}. "
                "Start PipeWire/PulseAudio, then retry."
            )

        mic_exists = any(
            virtual_mic_name in line.split("\t") or virtual_mic_description in line.split("\t")
            for line in sources_check.stdout.splitlines()
        )
        if not mic_exists:
            try:
                mic_created = subprocess.run(
                    [
                        "pactl",
                        "load-module",
                        "module-remap-source",
                        f"source_name={virtual_mic_name}",
                        f"source_properties=device.description={virtual_mic_description}",
                        f"master={sink_name}.monitor",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
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

    @staticmethod
    def _is_our_block(block: str) -> bool:
        """True when a ``pactl list sink-inputs`` block belongs to this process.

        Matches by process ID (PulseAudio-native clients, quoted or not) or by
        the ALSA application name (ALSA clients lack a PID field on PipeWire).
        """
        pid = os.getpid()
        pid_tokens = (
            f'application.process.id = "{pid}"',
            f"application.process.id = {pid}",
            f'application.process.id="{pid}"',
        )
        if any(t in block for t in pid_tokens):
            return True
        try:
            py_exe = os.path.basename(os.path.realpath(sys.executable))
        except OSError:
            py_exe = os.path.basename(sys.executable)
        # Fallback: match any CriTTS stream (covers edge_tts naming quirks)
        # ponytail: naive substring check; proper fix would parse pactl JSON if it existed
        return f"PipeWire ALSA [{py_exe}]" in block or ("CriTTS" in block and "PipeWire ALSA" in block)

    @classmethod
    def _list_our_sink_inputs(cls, timeout: float) -> Optional[list]:
        """Return this process's sink-input IDs (ascending), or None on failure."""
        try:
            result = subprocess.run(
                ["pactl", "list", "sink-inputs"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None

        ids = []
        for block in result.stdout.split("Sink Input #")[1:]:
            if not cls._is_our_block(block):
                continue
            # ponytail: regex is sturdier than split()[0] on indented/empty lines
            m = re.match(r"\s*(\d+)", block.split("\n", 1)[0])
            if m:
                ids.append(int(m.group(1)))
        return sorted(ids)

    def begin_stream_open(self, route: bool, *, keep_on_default: bool = False) -> "StreamOpenTicket":
        """Reserve the right to open one output stream; call right before opening it.

        Blocking (lock wait + one ``pactl`` call), so async callers run it via
        ``asyncio.to_thread``.  The returned ticket holds a process-wide lock
        until the new stream's sink input has been seen, so no other stream of
        this process (a voice preview, mic passthrough) can appear in between:
        the one new sink input is unambiguously ours.  Unrouted streams take a
        ticket too, so they never land inside a routed stream's window.

        *keep_on_default* moves an unrouted stream to the default sink.  PipeWire's
        stream-restore remembers the sink per application name, so once a TTS
        stream has been moved to our sink every later stream of this process
        (e.g. a voice preview) would otherwise open there too.

        Call :meth:`StreamOpenTicket.opened` once the stream has started and
        :meth:`StreamOpenTicket.close` when playback ends (or never started).
        """
        if not self.is_linux:
            return StreamOpenTicket(self, acquired=False, baseline=None, sink_name="")
        acquired = self._open_lock.acquire(timeout=self._OPEN_LOCK_TIMEOUT)
        if not acquired:
            logger.warning("Timed out waiting for the stream-open lock; opening without it")
        baseline = self._list_our_sink_inputs(timeout=1)
        if route:
            sink_name = self._sink_name
        else:
            sink_name = "@DEFAULT_SINK@" if keep_on_default and self._sink_name else ""
        if sink_name and baseline is None:
            # Without a baseline the new stream cannot be told apart from
            # existing ones; skip routing rather than move the wrong stream.
            logger.warning("Could not list sink inputs; not routing this stream to '%s'", sink_name)
            sink_name = ""
        return StreamOpenTicket(self, acquired=acquired, baseline=set(baseline or []), sink_name=sink_name)

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
                result = subprocess.run([pactl, "info"], capture_output=True, text=True, timeout=3)
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
                    result = subprocess.run(["pw-cli", "info", "0"], capture_output=True, text=True, timeout=3)
                    if result.returncode == 0:
                        detected = "pipewire"
            except Exception:
                logger.debug("PipeWire probe via pactl failed", exc_info=True)

        self._cached_audio_system = detected
        return detected


class StreamOpenTicket:
    """One output-stream open, from just before opening until its sink input is known.

    Created by :meth:`LinuxSinkManager.begin_stream_open`.  A ticket with an
    empty *sink_name* only holds the lock until its stream shows up.
    """

    _POLL_INTERVAL = 0.05

    def __init__(self, manager: LinuxSinkManager, *, acquired: bool, baseline: Optional[set], sink_name: str):
        self._manager = manager
        self._acquired = acquired
        self._baseline = baseline
        self._sink_name = sink_name
        self._closed = threading.Event()
        self._release_guard = threading.Lock()

    def _release(self) -> None:
        with self._release_guard:
            if self._acquired:
                self._acquired = False
                self._manager._open_lock.release()

    def opened(self) -> None:
        """The stream has started: find its sink input (and move it) on a daemon thread."""
        if self._closed.is_set() or self._baseline is None or (not self._acquired and not self._sink_name):
            self._release()
            return
        threading.Thread(target=self._identify_and_route, daemon=True).start()

    def close(self) -> None:
        """Playback ended or never started: stop routing and free the lock. Idempotent."""
        self._closed.set()
        self._release()

    def _identify_and_route(self) -> None:
        manager = self._manager
        start = time.monotonic()
        sink_input_id: Optional[int] = None
        try:
            while not self._closed.is_set():
                elapsed = time.monotonic() - start
                if elapsed >= manager._ROUTE_TIMEOUT:
                    return
                if self._acquired and elapsed >= manager._IDENTIFY_TIMEOUT:
                    # Do not block other streams any longer; later polls may be
                    # ambiguous, so they only accept a single new sink input.
                    self._release()
                    if not self._sink_name:
                        return
                if sink_input_id is None:
                    ids = manager._list_our_sink_inputs(timeout=1) or []
                    new_ids = [i for i in ids if i not in self._baseline]
                    if len(new_ids) == 1 or (new_ids and self._acquired):
                        # Under the lock only our stream can be new.
                        sink_input_id = new_ids[-1]
                        self._release()
                        if not self._sink_name:
                            return
                if sink_input_id is not None and self._move(sink_input_id):
                    return
                self._closed.wait(self._POLL_INTERVAL)
        finally:
            self._release()

    def _move(self, sink_input_id: int) -> bool:
        try:
            mv = subprocess.run(
                ["pactl", "move-sink-input", str(sink_input_id), self._sink_name],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception:
            logger.debug("Sink-input routing failed", exc_info=True)
            return False
        if mv.returncode == 0:
            logger.debug("Routed sink-input %s to sink '%s'", sink_input_id, self._sink_name)
            return True
        # Sink not ready yet or the stream already ended; retry next poll.
        logger.warning("move-sink-input %s -> %s failed: %s", sink_input_id, self._sink_name, mv.stderr.strip()[:200])
        return False
