"""Automatic common-key handling for standalone Windows builds."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile


def _resource_dir() -> str:
    # PyInstaller --onefile extracts bundled files below _MEIPASS.
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)))


def _key_path() -> str:
    # Keep the generated key in a private temp directory rather than beside the
    # executable, so the program needs no write permission in its install folder.
    d = os.path.join(tempfile.gettempdir(), "vc64_240p")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "common-key.bin")


def get_common_key() -> bytes:
    path = _key_path()
    if not os.path.isfile(path) or os.path.getsize(path) != 16:
        exe = os.path.join(_resource_dir(), "gzinject.exe")
        if not os.path.isfile(exe):
            raise RuntimeError("Bundled gzinject.exe is missing")
        try:
            result = subprocess.run(
                [exe, "-a", "genkey", "-k", path],
                input="45e\n",
                text=True,
                capture_output=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            raise RuntimeError(f"Could not generate the Wii common key: {e}") from e
        if result.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) != 16:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"Could not generate the Wii common key: {detail}")
    with open(path, "rb") as f:
        key = f.read()
    if len(key) != 16:
        raise RuntimeError("Generated Wii common key is invalid")
    return key
