import subprocess
from pathlib import Path

import pytest

from clipper.facecam import clamp_region, detect_facecam, face_to_region, stable_face
from clipper.models import Rect

FACE = Rect(100, 800, 80, 80)
FACE_IMAGE = Path(__file__).parent / "data" / "face.png"


def test_stable_face_found_when_present_in_60_percent():
    frames = [[FACE]] * 6 + [[]] * 4
    assert stable_face(frames, 1920) == FACE


def test_stable_face_missing_below_60_percent():
    assert stable_face([[FACE]] * 5 + [[]] * 5, 1920) is None


def test_moving_faces_are_ignored():
    frames = [[Rect(i * 250, 300, 80, 80)] for i in range(7)]
    assert stable_face(frames, 1920) is None


def test_stable_face_wins_over_moving_game_faces():
    frames = [[Rect(i * 250, 300, 120, 120), FACE] for i in range(7)]
    assert stable_face(frames, 1920) == FACE


def test_stable_face_tolerance_is_10_percent_of_width():
    near = Rect(FACE.x + 150, FACE.y, 80, 80)  # centro a 150 px < 192
    far = Rect(FACE.x + 250, FACE.y, 80, 80)  # centro a 250 px > 192
    assert stable_face([[FACE]] * 5 + [[near]] + [[]] * 4, 1920) is not None
    assert stable_face([[FACE]] * 5 + [[far]] + [[]] * 4, 1920) is None


def test_stable_face_is_the_median_of_the_cluster():
    frames = [[Rect(100, 800, 80, 80)], [Rect(110, 804, 84, 84)], [Rect(104, 802, 82, 82)]]
    assert stable_face(frames, 1920) == Rect(104, 802, 82, 82)


def test_no_frames():
    assert stable_face([], 1920) is None


def test_region_has_cam_aspect_contains_face_and_fits_frame():
    r = face_to_region(FACE, 1920, 1080)
    assert r.w / r.h == pytest.approx(1080 / 768, rel=0.02)
    assert r.x <= FACE.x and r.x + r.w >= FACE.x + FACE.w
    assert r.y <= FACE.y and r.y + r.h >= FACE.y + FACE.h
    assert r.x >= 0 and r.y >= 0 and r.x + r.w <= 1920 and r.y + r.h <= 1080
    assert r.w % 2 == 0 and r.h % 2 == 0


def test_region_near_corner_is_shifted_inside():
    r = face_to_region(Rect(1850, 1010, 60, 60), 1920, 1080)
    assert r.x + r.w <= 1920 and r.y + r.h <= 1080
    assert r.x >= 0 and r.y >= 0


def test_region_for_a_face_bigger_than_the_frame_allows_is_shrunk_to_fit():
    r = face_to_region(Rect(100, 100, 400, 400), 640, 480)
    assert r.x >= 0 and r.y >= 0 and r.x + r.w <= 640 and r.y + r.h <= 480
    assert r.w / r.h == pytest.approx(1080 / 768, rel=0.03)


def test_clamp_region():
    assert clamp_region(Rect(1800, 1000, 400, 300), 1920, 1080) == Rect(1800, 1000, 120, 80)
    assert clamp_region(Rect(2000, 0, 100, 100), 1920, 1080) is None
    assert clamp_region(Rect(0, 720, 480, 360), 1920, 1080) == Rect(0, 720, 480, 360)


def test_clamp_region_keeps_even_dimensions():
    r = clamp_region(Rect(0, 0, 481, 361), 1920, 1080)
    assert r == Rect(0, 0, 480, 360)


def test_detect_facecam_returns_none_without_faces(make_video):
    assert detect_facecam(make_video()) is None


def test_detect_facecam_on_unreadable_file_returns_none(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_text("nope")
    assert detect_facecam(bad) is None


def test_detect_facecam_finds_a_real_face_in_a_corner(tmp_path):
    """Fotografia real (NASA, domínio público) colada como facecam sobre o jogo."""
    video = tmp_path / "stream.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=3",
            "-loop", "1", "-i", str(FACE_IMAGE),
            "-filter_complex", "[1:v]scale=240:240[f];[0:v][f]overlay=40:440:shortest=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
    )
    region = detect_facecam(video)
    assert region is not None
    # o rosto fica dentro do quadrado colado em (40..280, 440..680)
    assert region.x <= 120 and region.x + region.w >= 200
    assert region.y <= 500 and region.y + region.h >= 600
    assert region.x + region.w <= 1280 and region.y + region.h <= 720
    assert region.w / region.h == pytest.approx(1080 / 768, rel=0.03)
