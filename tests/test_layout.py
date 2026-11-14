from dataclasses import replace
from pathlib import Path

import pytest

from clipper.captions import Cue, build_ass
from clipper.facecam import clamp_region
from clipper import layout
from clipper.layout import (
    MAX_BYTES,
    RenderError,
    build_filter,
    render,
    render_cover,
    text_positions,
)
from clipper.media import MediaInfo, probe
from clipper.models import Rect

FONTS = Path(__file__).parent.parent / "assets" / "fonts"
INFO_1080P30 = MediaInfo(width=1920, height=1080, duration=30.0, fps=30.0, has_audio=True)


def render_with_ass(src, work_dir, *, facecam, title, max_bytes=MAX_BYTES):
    work_dir.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    ass = work_dir / "clip.ass"
    ass.write_text(
        build_ass(
            [Cue(0.5, 1.5, "HELLO WORLD")],
            title=title,
            credit="twitch.tv/shroud",
            duration=info.duration,
            **text_positions(facecam is not None),
        ),
        encoding="utf-8",
    )
    dst = work_dir / "out.mp4"
    render(src, dst, facecam=facecam, ass_path=ass, fonts_dir=FONTS, max_bytes=max_bytes)
    return dst


def test_text_positions():
    assert text_positions(True) == {"title_y": 1000, "caption_y": 768, "credit_y": 1480}
    assert text_positions(False) == {"title_y": 330, "caption_y": 1340, "credit_y": 1480}


@pytest.mark.parametrize("has_facecam", [True, False])
def test_text_stays_clear_of_the_platform_interface(has_facecam):
    """O YouTube Shorts e o TikTok tapam o topo e o fundo do vídeo com botões e legendas."""
    assert all(250 <= y <= 1500 for y in text_positions(has_facecam).values())


def test_filter_with_facecam_stacks_cam_over_game():
    f = build_filter(INFO_1080P30, Rect(0, 720, 480, 360), Path("a.ass"), Path("fonts"))
    assert "crop=480:360:0:720" in f and "vstack" in f and "1080:768" in f and "1080:1152" in f


def test_filter_without_facecam_uses_blurred_background():
    f = build_filter(INFO_1080P30, None, Path("a.ass"), Path("fonts"))
    assert "gblur" in f and "overlay=0:240" in f and "1080:1440" in f
    assert f.index("scale=270:480") < f.index("gblur")  # desfoca uma cópia pequena: mais rápido


def test_filter_caps_fps_at_60():
    assert "fps=60," in build_filter(replace(INFO_1080P30, fps=120.0), None, Path("a.ass"), Path("f"))
    assert "fps=30," in build_filter(INFO_1080P30, None, Path("a.ass"), Path("f"))


def test_filter_keeps_fractional_fps():
    assert "fps=29.97," in build_filter(replace(INFO_1080P30, fps=29.97), None, Path("a.ass"), Path("f"))


@pytest.mark.parametrize("facecam", [None, Rect(0, 600, 480, 360)])
@pytest.mark.parametrize("size", [(1920, 1080), (1280, 720), (640, 480), (720, 1280)])
def test_render_output_is_always_1080x1920(make_video, tmp_path, size, facecam):
    src = make_video(width=size[0], height=size[1])
    cam = clamp_region(facecam, *size) if facecam else None
    dst = render_with_ass(src, tmp_path / "w", facecam=cam, title="it's {5}:00 \\ 🔥\nnew line")
    info = probe(dst)
    assert (info.width, info.height, info.has_audio) == (1080, 1920, True)
    assert info.duration == pytest.approx(3, abs=0.3)


def test_render_source_without_audio(make_video, tmp_path):
    info = probe(render_with_ass(make_video(audio=False), tmp_path / "w", facecam=None, title="t"))
    assert (info.width, info.height, info.has_audio) == (1080, 1920, False)


def test_render_caps_output_fps_at_60(make_video, tmp_path):
    dst = render_with_ass(make_video(fps=120, seconds=1), tmp_path / "w", facecam=None, title="t")
    assert probe(dst).fps == pytest.approx(60)


def test_render_works_from_a_folder_with_awkward_characters(make_video, tmp_path):
    work = tmp_path / "it's a [dir], x:y;z"
    info = probe(render_with_ass(make_video(seconds=1), work, facecam=None, title="t"))
    assert (info.width, info.height) == (1080, 1920)


def test_render_recompresses_to_fit_limit(make_video, tmp_path):
    src = make_video(seconds=5)
    full = render_with_ass(src, tmp_path / "full", facecam=None, title="t").stat().st_size
    limit = int(full * 0.7)
    dst = render_with_ass(src, tmp_path / "small", facecam=None, title="t", max_bytes=limit)
    assert dst.stat().st_size <= limit


def test_render_raises_when_limit_is_impossible(make_video, tmp_path):
    with pytest.raises(RenderError):
        render_with_ass(make_video(), tmp_path / "w", facecam=None, title="t", max_bytes=1_000)
    assert not (tmp_path / "w" / "out.mp4").exists()


def test_render_failure_raises_render_error(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_text("nope")
    with pytest.raises(RenderError):
        render(bad, tmp_path / "o.mp4", facecam=None, ass_path=tmp_path / "x.ass", fonts_dir=FONTS)


def test_render_fits_a_tight_limit_in_a_single_encode(make_video, tmp_path, monkeypatch):
    src = make_video(seconds=5)
    full = render_with_ass(src, tmp_path / "full", facecam=None, title="t").stat().st_size
    encodes = []
    real_run = layout.subprocess.run

    def counting_run(command, *args, **kwargs):
        if command[0] == "ffmpeg":
            encodes.append(command)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(layout.subprocess, "run", counting_run)
    limit = int(full * 0.7)
    dst = render_with_ass(src, tmp_path / "small", facecam=None, title="t", max_bytes=limit)
    assert dst.stat().st_size <= limit
    assert len(encodes) == 1


def test_one_encode_can_never_outlive_the_github_job():
    assert layout.TIMEOUT <= 300


def hevc_source(tmp_path):
    """A Twitch entrega clips em HEVC, não só em H.264."""
    import subprocess

    path = tmp_path / "hevc.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=60:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )
    return path


def test_render_accepts_hevc_clips_and_outputs_h264(tmp_path):
    import json
    import subprocess

    dst = render_with_ass(hevc_source(tmp_path), tmp_path / "w", facecam=None, title="t")
    info = probe(dst)
    assert (info.width, info.height, info.has_audio) == (1080, 1920, True)
    streams = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-of", "json", "-show_streams", str(dst)],
            capture_output=True, text=True, check=True,
        ).stdout
    )["streams"]
    assert {s["codec_name"] for s in streams} == {"h264", "aac"}


def test_facecam_detection_reads_hevc_clips(tmp_path, monkeypatch):
    from clipper import facecam

    frames = []
    real = facecam.stable_face
    monkeypatch.setattr(facecam, "stable_face", lambda boxes, w: frames.append(len(boxes)) or real(boxes, w))
    assert facecam.detect_facecam(hevc_source(tmp_path)) is None
    assert frames == [10]  # os 10 fotogramas foram mesmo lidos


def test_filter_with_flash_puts_the_peak_before_the_clip():
    # O troço do pico chega como entrada 0 (já cortada pelo -ss/-t) e o clip
    # inteiro como entrada 1: nada fica à espera em memória.
    f = build_filter(INFO_1080P30, None, Path("a.ass"), Path("fonts"), flash=(12.0, 1.5))
    assert "[0:v]setpts=PTS-STARTPTS[v1]" in f and "[1:v]setpts=PTS-STARTPTS[v2]" in f
    assert "[0:a]asetpts" in f and "[1:a]asetpts" in f
    assert "concat=n=2:v=1:a=1[src][a]" in f
    assert "split=2[fv]" not in f and "trim=" not in f
    assert f.count("[src]") == 2  # produzido pela concatenação e usado pelo enquadramento


def test_filter_with_flash_and_no_audio_concatenates_only_video():
    info = replace(INFO_1080P30, has_audio=False)
    f = build_filter(info, None, Path("a.ass"), Path("fonts"), flash=(3.0, 1.5))
    assert "concat=n=2:v=1:a=0[src]" in f and "asetpts" not in f


def test_render_with_flash_reads_the_peak_as_a_separate_input(make_video, tmp_path, monkeypatch):
    seen = {}
    real_run = layout.subprocess.run

    def spy(command, **kwargs):
        if command[0] == "ffmpeg":
            seen["command"] = command
        return real_run(command, **kwargs)

    monkeypatch.setattr(layout.subprocess, "run", spy)
    src = make_video(seconds=10)
    ass = tmp_path / "a.ass"
    ass.write_text(build_ass([], title="H", credit="c", duration=11.5, **text_positions(False)),
                   encoding="utf-8")
    render(src, tmp_path / "o.mp4", facecam=None, ass_path=ass, fonts_dir=FONTS, flash=(6.0, 1.5))
    command = seen["command"]
    first = command.index("-i")
    assert command[first - 4 : first] == ["-ss", "6", "-t", "1.5"]
    assert command.count("-i") == 2


@pytest.mark.parametrize("audio", [True, False])
def test_render_with_flash_adds_its_length(make_video, tmp_path, audio):
    src = make_video(seconds=10, audio=audio)
    ass = tmp_path / "a.ass"
    ass.write_text(build_ass([], title="HOOK", credit="c", duration=11.5, **text_positions(False)),
                   encoding="utf-8")
    dst = tmp_path / "out.mp4"
    render(src, dst, facecam=None, ass_path=ass, fonts_dir=FONTS, flash=(6.0, 1.5))
    info = probe(dst)
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration == pytest.approx(11.5, abs=0.2)
    assert info.has_audio == audio


@pytest.mark.parametrize("facecam", [None, Rect(0, 720, 480, 360)])
def test_render_cover_is_a_vertical_jpeg(make_video, tmp_path, facecam):
    src = make_video(seconds=5)
    ass = tmp_path / "cover.ass"
    ass.write_text(build_ass([], title="HE DID WHAT", credit="twitch.tv/x", duration=1.0,
                             **text_positions(facecam is not None)), encoding="utf-8")
    dst = tmp_path / "cover.jpg"
    render_cover(src, dst, facecam=facecam, ass_path=ass, fonts_dir=FONTS, at=2.0)
    assert dst.read_bytes()[:2] == b"\xff\xd8"
    info = probe(dst)
    assert (info.width, info.height) == (1080, 1920)
    assert dst.stat().st_size < 1_000_000


def test_render_cover_failure_raises_render_error(tmp_path):
    with pytest.raises(RenderError):
        render_cover(tmp_path / "missing.mp4", tmp_path / "c.jpg", facecam=None,
                     ass_path=tmp_path / "x.ass", fonts_dir=FONTS, at=0)
