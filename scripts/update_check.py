#!/usr/bin/env python3
"""Check GitHub for updates to CriTTS and apply if requested.

Usage:
    python scripts/update_check.py            # check only, print status
    python scripts/update_check.py --apply    # download and apply update

Strategy:
    Compares the locally stored .version file (a commit SHA) against the
    latest commit on the repo's default branch (via GitHub API).  If they
    differ, downloads the branch zipball and extracts it, preserving user
    data (settings.json, venv, etc.).
"""
import json
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = SCRIPT_DIR / ".version"

REPO = "crisbbc/CriTTS"
BRANCH = "main"

BRANCH_API = f"https://api.github.com/repos/{REPO}/branches/{BRANCH}"
ZIPBALL_URL = f"https://api.github.com/repos/{REPO}/zipball/{BRANCH}"
ZIPBALL_BY_SHA_URL = f"https://api.github.com/repos/{REPO}/zipball/{{sha}}"

# Files/directories to preserve during update (never overwrite)
PRESERVE = {
    "settings.json",
    ".version",
    ".dep-hash",
    "venv",
    ".venv",
    "__pycache__",
}

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "CriTTS-Updater/2.0",
}


def _api_get(url: str, timeout: int = 15) -> dict | bytes:
    """Perform a GET request with standard headers."""
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=timeout) as resp:
        content = resp.read()
    ct = resp.headers.get("Content-Type", "")
    if "json" in ct:
        return json.loads(content)
    return content


def get_remote_sha() -> str:
    """Return the latest commit SHA on the default branch."""
    data = _api_get(BRANCH_API, timeout=15)
    return data["commit"]["sha"]


def get_local_sha() -> str | None:
    """Return the locally stored commit SHA, if any."""
    if VERSION_FILE.exists():
        sha = VERSION_FILE.read_text().strip()
        # Validate full hex commit hashes only (40-char SHA-1 or 64-char SHA-256).
        if len(sha) in (40, 64) and all(c in "0123456789abcdef" for c in sha):
            return sha
    return None


def write_local_sha(sha: str) -> None:
    VERSION_FILE.write_text(sha + "\n")


def _safe_extract_zip(zip_path: Path, destination: Path) -> Path:
    """Safely extract a single GitHub-style top-level directory.

    Zip archives are untrusted input.  Reject absolute paths, traversal,
    entries outside one top-level directory, and symlink entries before any
    file is written.
    """
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        if not members:
            raise ValueError("Update archive is empty")

        root_parts = None
        for member in members:
            path = Path(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe update archive member: {member.filename!r}")
            parts = path.parts
            if not parts:
                continue
            if root_parts is None:
                root_parts = parts[0]
            if parts[0] != root_parts:
                raise ValueError("Update archive must contain one top-level directory")
            mode = (member.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError(f"Symlink entries are not allowed: {member.filename!r}")

        if not root_parts:
            raise ValueError("Update archive has no top-level directory")

        for member in members:
            target = destination / Path(member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.is_dir():
                target.mkdir(exist_ok=True)
                continue
            with zf.open(member) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output)

        return destination / root_parts


def _remove_path(path: Path) -> None:
    """Remove a file, directory, or symlink without following symlinks."""
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _purge_bytecode() -> None:
    """Delete __pycache__ directories under SCRIPT_DIR.

    The updater preserves existing files, so a module removed from the new
    revision would otherwise remain importable through stale bytecode left in
    __pycache__.  Removing the caches forces Python to regenerate them from the
    current sources.
    """
    for pycache in SCRIPT_DIR.rglob("__pycache__"):
        try:
            if pycache.is_dir():
                shutil.rmtree(pycache)
            elif pycache.is_symlink():
                pycache.unlink(missing_ok=True)
        except OSError:
            pass


def _apply_staged_update(extracted: Path) -> None:
    """Apply a validated update with rollback if any top-level copy fails."""
    backup_root = Path(tempfile.mkdtemp(prefix="critts-update-backup-", dir=SCRIPT_DIR.parent))
    transitions = []
    retain_backup = False
    items = [item for item in extracted.iterdir() if item.name not in PRESERVE]
    try:
        for item in items:
            dest = SCRIPT_DIR / item.name
            backup = backup_root / item.name
            had_original = dest.exists() or dest.is_symlink()
            transition = {"dest": dest, "backup": backup, "had_original": had_original, "moved": False}
            transitions.append(transition)

            if had_original:
                shutil.move(str(dest), str(backup))
                transition["moved"] = True

            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
    except Exception as apply_error:
        # Restore only originals confirmed to have moved.  If a move failed
        # before producing a backup, leave the original destination untouched.
        try:
            for transition in reversed(transitions):
                dest = transition["dest"]
                backup = transition["backup"]
                had_original = transition["had_original"]
                moved = transition["moved"]

                if had_original:
                    if backup.exists() or backup.is_symlink():
                        _remove_path(dest)
                        shutil.move(str(backup), str(dest))
                    elif moved:
                        raise RuntimeError(f"Original backup missing for {dest}")
                elif dest.exists() or dest.is_symlink():
                    _remove_path(dest)
        except Exception as rollback_error:
            retain_backup = True
            raise RuntimeError(
                "Update failed and rollback failed; backup retained at "
                f"{backup_root}"
            ) from rollback_error
        raise apply_error

    finally:
        if not retain_backup:
            shutil.rmtree(backup_root, ignore_errors=True)


def download_and_apply(zipball_url: str) -> None:
    """Download the branch zipball and extract into SCRIPT_DIR.

    Preserves user-config files so settings, venv, and state are not wiped.
    """
    print("Downloading update...")
    zip_data = _api_get(zipball_url, timeout=120)

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "update.zip"
        zip_path.write_bytes(zip_data)

        extracted = _safe_extract_zip(zip_path, Path(tmp))
        _apply_staged_update(extracted)

    # After extracting new code, invalidate dep-hash so deps get reinstalled
    dep_hash = SCRIPT_DIR / ".dep-hash"
    if dep_hash.exists():
        dep_hash.unlink()

    # Remove stale bytecode so a deleted module can't be imported from an old
    # .pyc still present in __pycache__.
    _purge_bytecode()

    print("Update applied successfully.")


def main() -> None:
    local_sha = get_local_sha()

    try:
        remote_sha = get_remote_sha()
    except Exception as e:
        print(f"Failed to check for updates: {e}", file=sys.stderr)
        sys.exit(1)

    if local_sha == remote_sha:
        print(f"Already at latest: {remote_sha[:12]}")
        sys.exit(0)

    print(f"Update available: {local_sha[:12] if local_sha else 'none'} -> {remote_sha[:12]}")

    if len(sys.argv) > 1 and sys.argv[1] == "--apply":
        try:
            # Pin the archive to the exact commit that was checked above;
            # downloading the moving branch name could install different code.
            download_and_apply(ZIPBALL_BY_SHA_URL.format(sha=remote_sha))
        except Exception as e:
            print(f"Update failed during download/extract: {e}", file=sys.stderr)
            # Don't write .version on failure -- let next run retry
            sys.exit(1)

        write_local_sha(remote_sha)
        print(f"Updated to {remote_sha[:12]}. Restart to run the new version.")
    else:
        print("Run with --apply to install this update.")


if __name__ == "__main__":
    main()
