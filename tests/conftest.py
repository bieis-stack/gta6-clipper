import itertools
import subprocess

import pytest


@pytest.fixture
def make_video(tmp_path):
    """Fábrica de vídeos sintéticos gerados pelo ffmpeg."""
    counter = itertools.count()

    def _make(*, width=1920, height=1080, seconds=3, fps=30, audio=True):
        path = tmp_path / f"source{next(counter)}.mp4"
        command = [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}:duration={seconds}",
        ]
        if audio:
            command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        command += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
        if audio:
            command += ["-c:a", "aac", "-shortest"]
        command.append(str(path))
        subprocess.run(command, check=True)
        return path

    return _make
