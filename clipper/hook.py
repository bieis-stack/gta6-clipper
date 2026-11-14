"""Escolha do momento mais forte de um clip, para abrir o vídeo com ele.

Os momentos que os espectadores clipam são quase sempre gritos e reações, por
isso o troço com mais energia no áudio é um bom gancho: o vídeo mostra-o
primeiro e depois recomeça o clip desde o início.
"""

from __future__ import annotations

import numpy as np

STEP = 0.1  # segundos entre janelas candidatas
MIN_CLIP = 8.0  # clips mais curtos não têm tempo para um flash-forward
MIN_START = 2.0  # se o pico estiver logo no início, o clip já abre forte
MIN_ENERGY = 1e-6  # abaixo disto é silêncio


def loudest_window(audio: np.ndarray, rate: int, *, window: float) -> float | None:
    """Início (em segundos) da janela com mais energia, ou None se o áudio for curto."""
    size = int(round(window * rate))
    if size <= 0 or audio.size < size:
        return None
    power = np.concatenate(([0.0], np.cumsum(audio.astype(np.float64) ** 2)))
    hop = max(int(round(STEP * rate)), 1)
    starts = np.arange(0, audio.size - size + 1, hop)
    energy = power[starts + size] - power[starts]
    return float(starts[int(np.argmax(energy))] / rate)


def choose_flash(audio: np.ndarray, rate: int, *, seconds: float) -> float | None:
    """Início do troço a mostrar antes do clip, ou None se não valer a pena."""
    if seconds <= 0 or audio.size < MIN_CLIP * rate:
        return None
    start = loudest_window(audio, rate, window=seconds)
    if start is None or start < MIN_START:
        return None
    piece = audio[int(start * rate) : int((start + seconds) * rate)].astype(np.float64)
    if float(np.mean(piece**2)) < MIN_ENERGY:
        return None
    return start
