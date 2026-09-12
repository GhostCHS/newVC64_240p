import os
import subprocess
import sys
import tempfile


def common_key_path():
    root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)))
    target = os.path.join(tempfile.gettempdir(), "vc64_240p", "common-key.bin")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not os.path.isfile(target) or os.path.getsize(target) != 16:
        tool = os.path.join(root, "gzinject.exe")
        if not os.path.isfile(tool):
            raise RuntimeError("Automatic key generator is missing from this build.")
        r = subprocess.run([tool, "-a", "genkey", "-k", target], input="45e\n", text=True,
                           capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0 or not os.path.isfile(target) or os.path.getsize(target) != 16:
            raise RuntimeError((r.stderr or r.stdout or "Key generation failed.").strip())
    return target
