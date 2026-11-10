"""seam/util.py: helpers shared by the seam tools."""
import hashlib

from seam import util, video


def test_sha256_file(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"x" * 3_000_000)
    assert util.sha256_file(p) == hashlib.sha256(b"x" * 3_000_000).hexdigest()


def test_ffmpeg_version_and_the_old_import_paths():
    assert util.ffmpeg_version().startswith("ffmpeg version")
    assert video.ffmpeg_version is util.ffmpeg_version
    from seam import controls_inputs, ingest, lines_job
    assert ingest.sha256_file is util.sha256_file and controls_inputs.sha256_file is util.sha256_file
    assert lines_job.sha256_file is util.sha256_file
