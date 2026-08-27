"""Minimal WayVR launcher helper — ponytail: stdlib only, YAGNI."""

import os
from pathlib import Path


def _runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


def get_wayvr_display() -> str | None:
    """Return WAYLAND_DISPLAY value for WayVR, or None if not running.

    Reads ``$XDG_RUNTIME_DIR/wayvr.disp`` (WayVR's socket marker) and falls back
    to probing ``wayland-20``.  Returns e.g. ``\"wayland-20\"``.
    """
    # ponytail: one probe, no daemon, no IPC dependency
    disp_file = _runtime_dir() / "wayvr.disp"
    try:
        if disp_file.is_file():
            val = disp_file.read_text(encoding="utf-8").strip()
            if val:
                # file contains e.g. "wayland-20" or just "20"
                if val.startswith("wayland-"):
                    return val
                if val.isdigit():
                    return f"wayland-{val}"
                return val
    except Exception:
        pass

    # Fallback: WayVR defaults to wayland-20; check socket exists
    for name in ("wayland-20", "wayland-wayvr"):
        if (_runtime_dir() / name).exists():
            return name
    return None


def is_wayvr_available() -> bool:
    return get_wayvr_display() is not None


def is_running_in_wayvr() -> bool:
    disp = os.environ.get("WAYLAND_DISPLAY", "")
    wayvr = get_wayvr_display()
    return bool(wayvr and disp == wayvr)


def build_wayvr_env(base: dict | None = None) -> dict | None:
    """Return env dict to launch inside WayVR, or None if unavailable."""
    disp = get_wayvr_display()
    if not disp:
        return None
    env = dict(base or os.environ)
    env["WAYLAND_DISPLAY"] = disp
    env["DISPLAY"] = ""  # force Wayland
    return env
