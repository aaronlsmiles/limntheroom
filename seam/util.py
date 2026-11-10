"""Small helpers shared by the seam tools (stdlib only, so every venv can import it)."""
import hashlib
import subprocess


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ffmpeg_version():
    """The first line of `ffmpeg -version`."""
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout
    return out.splitlines()[0].strip()
