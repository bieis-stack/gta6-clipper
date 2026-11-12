"""Deteção da zona da facecam num vídeo de stream."""

from __future__ import annotations

from pathlib import Path
from statistics import median

import cv2

from clipper.models import Rect

DEFAULT_MODEL = (
    Path(__file__).resolve().parent.parent / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
)
CAM_ASPECT = 1080 / 768
MIN_PRESENCE = 0.6
TOLERANCE = 0.10
SCORE_THRESHOLD = 0.8
# Altura da zona recortada, em alturas de rosto, e quanto desce o seu centro em
# relação ao do rosto. Afinado com clips reais: apertado o bastante para a
# câmara encher a faixa, com folga para auscultadores em cima e ombros em baixo.
REGION_HEIGHT = 2.3
REGION_SHIFT = 0.1


def _even(value: float) -> int:
    return int(value) // 2 * 2


def _center(box: Rect) -> tuple[float, float]:
    return box.x + box.w / 2, box.y + box.h / 2


def stable_face(boxes_per_frame: list[list[Rect]], frame_w: int) -> Rect | None:
    """O rosto que aparece no mesmo sítio na maioria dos fotogramas.

    Rostos de personagens do jogo mexem-se; o do streamer não.
    """
    if not boxes_per_frame:
        return None
    tolerance = TOLERANCE * frame_w
    best: list[Rect] = []
    for anchor in (box for boxes in boxes_per_frame for box in boxes):
        ax, ay = _center(anchor)
        cluster = []
        for boxes in boxes_per_frame:
            near = [
                (abs(_center(box)[0] - ax) + abs(_center(box)[1] - ay), box)
                for box in boxes
                if abs(_center(box)[0] - ax) < tolerance and abs(_center(box)[1] - ay) < tolerance
            ]
            if near:
                cluster.append(min(near, key=lambda pair: pair[0])[1])
        if len(cluster) > len(best):
            best = cluster
    if len(best) / len(boxes_per_frame) < MIN_PRESENCE:
        return None
    return Rect(*(int(median(getattr(box, name) for box in best)) for name in ("x", "y", "w", "h")))


def face_to_region(face: Rect, frame_w: int, frame_h: int) -> Rect:
    """Alarga o rosto até uma zona com o formato da faixa da facecam."""
    height = REGION_HEIGHT * face.h
    width = height * CAM_ASPECT
    shrink = min(1.0, frame_w / width, frame_h / height)
    w, h = _even(width * shrink), _even(height * shrink)
    cx, cy = _center(face)
    cy += REGION_SHIFT * face.h
    x = min(max(int(cx - w / 2), 0), frame_w - w)
    y = min(max(int(cy - h / 2), 0), frame_h - h)
    return Rect(x, y, w, h)


def clamp_region(region: Rect, frame_w: int, frame_h: int) -> Rect | None:
    """Corta uma zona indicada à mão ao que cabe na imagem; None se ficar de fora."""
    x, y = max(region.x, 0), max(region.y, 0)
    w = _even(min(region.x + region.w, frame_w) - x)
    h = _even(min(region.y + region.h, frame_h) - y)
    if w < 2 or h < 2:
        return None
    return Rect(x, y, w, h)


def _sample_frames(video: Path, samples: int):
    capture = cv2.VideoCapture(str(video))
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not capture.isOpened() or total <= 0:
            return
        for index in range(samples):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int((index + 0.5) * total / samples))
            ok, frame = capture.read()
            if ok:
                yield frame
    finally:
        capture.release()


def detect_facecam(video: Path, samples: int = 10, model: Path = DEFAULT_MODEL) -> Rect | None:
    boxes_per_frame: list[list[Rect]] = []
    size = None
    detector = None
    for frame in _sample_frames(video, samples):
        height, width = frame.shape[:2]
        if detector is None:
            size = (width, height)
            detector = cv2.FaceDetectorYN.create(str(model), "", size, SCORE_THRESHOLD)
        _, faces = detector.detect(frame)
        boxes_per_frame.append(
            [Rect(*(int(value) for value in face[:4])) for face in (faces if faces is not None else [])]
        )
    if size is None:
        return None
    face = stable_face(boxes_per_frame, size[0])
    if face is None:
        return None
    return clamp_region(face_to_region(face, *size), *size)
