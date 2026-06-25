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
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = SCRIPT_DIR / ".version"

REPO = "k1rk11/CriTTS"
BRANCH = "main"

BRANCH_API = f"https://api.github.com/repos/{REPO}/branches/{BRANCH}"
ZIPBALL_URL = f"https://api.github.com/repos/{REPO}/zipball/{BRANCH}"

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
        # Validate hex format (40-char)
        if len(sha) >= 40 and all(c in "0123456789abcdef" for c in sha):
            return sha
    return None


def write_local_sha(sha: str) -> None:
    VERSION_FILE.write_text(sha + "\n")


def download_and_apply(zipball_url: str) -> None:
    """Download the branch zipball and extract into SCRIPT_DIR.

    Preserves user-config files so settings, venv, and state are not wiped.
    """
    print("Downloading update...")
    zip_data = _api_get(zipball_url, timeout=120)

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "update.zip"
        zip_path.write_bytes(zip_data)

        with zipfile.ZipFile(zip_path) as zf:
            # GitHub zipballs wrap everything in a dir named "REPO-BRANCH"
            root = zf.namelist()[0].split("/")[0]
            zf.extractall(tmp)

        extracted = Path(tmp) / root

        for item in extracted.iterdir():
            dest = SCRIPT_DIR / item.name
            if item.name in PRESERVE:
                continue
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    # After extracting new code, invalidate dep-hash so deps get reinstalled
    dep_hash = SCRIPT_DIR / ".dep-hash"
    if dep_hash.exists():
        dep_hash.unlink()

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
            download_and_apply(ZIPBALL_URL)
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
