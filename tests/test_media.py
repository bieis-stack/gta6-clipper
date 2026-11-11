import pytest

from clipper.media import MediaError, probe


def test_probe(make_video):
    info = probe(make_video(width=1280, height=720, seconds=2, fps=60))
    assert (info.width, info.height, info.has_audio) == (1280, 720, True)
    assert info.fps == pytest.approx(60)
    assert info.duration == pytest.approx(2, abs=0.2)


def test_probe_without_audio(make_video):
    assert probe(make_video(audio=False)).has_audio is False


def test_probe_not_a_video(tmp_path):
    p = tmp_path / "x.mp4"
    p.write_text("nope")
    with pytest.raises(MediaError):
        probe(p)


def test_probe_missing_file(tmp_path):
    with pytest.raises(MediaError):
        probe(tmp_path / "missing.mp4")
