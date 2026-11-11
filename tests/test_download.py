import pytest
import yt_dlp

from clipper.download import DownloadError, download_clip


class FakeYDL:
    """Substitui o YoutubeDL: cria o ficheiro que o verdadeiro descarregaria."""

    error = None
    seen_options = None

    def __init__(self, options):
        FakeYDL.seen_options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        if FakeYDL.error:
            raise FakeYDL.error
        return {"id": "Abc", "ext": "mp4"}

    def prepare_filename(self, info):
        path = FakeYDL.seen_options["outtmpl"] % info
        with open(path, "wb") as handle:
            handle.write(b"video")
        return path


@pytest.fixture
def fake_ydl(monkeypatch):
    FakeYDL.error = None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_download_returns_file_path(fake_ydl, tmp_path):
    path = download_clip("https://clips.twitch.tv/Abc", tmp_path / "work")
    assert path == tmp_path / "work" / "Abc.mp4"
    assert path.read_bytes() == b"video"


def test_download_wraps_errors(fake_ydl, tmp_path):
    fake_ydl.error = yt_dlp.utils.DownloadError("clip removed")
    with pytest.raises(DownloadError, match="clip removed"):
        download_clip("https://clips.twitch.tv/Abc", tmp_path)


def test_download_without_resulting_file_is_an_error(fake_ydl, tmp_path, monkeypatch):
    monkeypatch.setattr(fake_ydl, "prepare_filename", lambda self, info: str(tmp_path / "nope.mp4"))
    with pytest.raises(DownloadError):
        download_clip("https://clips.twitch.tv/Abc", tmp_path)
