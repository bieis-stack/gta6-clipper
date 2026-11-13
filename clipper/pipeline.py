"""Orquestração de uma execução completa: procurar, escolher, editar e entregar."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from clipper.captions import build_ass, group_words, transcribe
from clipper.config import Config
from clipper.download import download_clip
from clipper.facecam import clamp_region, detect_facecam
from clipper.layout import render, text_positions
from clipper.media import probe
from clipper.metadata import build_description, build_title
from clipper.models import Clip, RenderedClip, Streamer
from clipper.publishers.base import Publisher
from clipper.selection import eligible, select
from clipper.state import State
from clipper.twitch import TwitchAuthError, TwitchClient, TwitchError

log = logging.getLogger(__name__)

FACE_MODEL = Path("models") / "face_detection_yunet_2023mar.onnx"


class GameNotFound(Exception):
    pass


@dataclass(frozen=True)
class RunSummary:
    candidates: int
    delivered: int
    failed: int
    waiting: int = 0  # escolhidos mas não tratados, por não haver destino


def process_clip(
    clip: Clip, streamer: Streamer, config: Config, work_dir: Path, assets_dir: Path
) -> RenderedClip:
    """Descarrega um clip e devolve-o editado em vertical, com os textos de publicação."""
    work_dir, assets_dir = Path(work_dir), Path(assets_dir)
    source = download_clip(clip.url, work_dir)
    info = probe(source)

    facecam = None
    if streamer.facecam is not None:
        facecam = clamp_region(streamer.facecam, info.width, info.height)
        if facecam is None:
            log.warning(
                "a zona de facecam configurada para %s fica fora da imagem (%dx%d); "
                "a usar a deteção automática",
                streamer.twitch, info.width, info.height,
            )
    if facecam is None:
        facecam = detect_facecam(source, model=assets_dir / FACE_MODEL)

    try:
        words = transcribe(source)
    except Exception as error:  # um clip sem legendas vale mais do que nenhum clip
        log.warning("clip %s sem legendas: a transcrição falhou (%s)", clip.id, error)
        words = []

    ass_path = work_dir / f"{clip.id}.ass"
    ass_path.write_text(
        build_ass(
            group_words(words),
            title=clip.title,
            credit=f"twitch.tv/{clip.broadcaster_login}",
            duration=info.duration,
            **text_positions(facecam is not None),
        ),
        encoding="utf-8",
    )
    final = work_dir / f"{clip.id}_final.mp4"
    render(source, final, facecam=facecam, ass_path=ass_path, fonts_dir=assets_dir / "fonts")

    tag = config.hashtags[0] if config.hashtags else ""
    return RenderedClip(
        clip=clip,
        video_path=final,
        title=build_title(clip.title, clip.broadcaster_name, tag),
        description=build_description(clip, config.hashtags),
    )


def run(
    config: Config,
    state: State,
    twitch: TwitchClient,
    publisher: Publisher | None,
    *,
    now: datetime,
    process: Callable[[Clip, Streamer], RenderedClip],
    checkpoint: Callable[[], None] | None = None,
    out_of_time: Callable[[], bool] | None = None,
) -> RunSummary:
    """`checkpoint` grava o estado antes e depois de cada clip: assim uma
    execução interrompida a meio não reenvia o que já entregou.
    `out_of_time` diz se já não há tempo para começar mais um clip.
    Sem `publisher`, só conta os clips que entregaria, sem os editar nem gastar."""
    state.prune(now)
    if not config.streamers:
        log.warning("nenhum streamer configurado em config.yaml; nada a fazer")
        return RunSummary(0, 0, 0)

    game_id = twitch.get_game_id(config.game_name)
    if game_id is None:
        raise GameNotFound(f"a Twitch não tem nenhum jogo chamado '{config.game_name}'")

    users = twitch.get_users([streamer.twitch for streamer in config.streamers])
    started_at = now - timedelta(hours=config.selection.lookback_hours)
    clips: list[Clip] = []
    streamer_of: dict[str, Streamer] = {}
    for streamer in config.streamers:
        user = users.get(streamer.twitch)
        if user is None:
            log.warning("o canal '%s' não existe na Twitch; ignorado", streamer.twitch)
            continue
        try:
            found = twitch.get_clips(user, started_at, now)
        except TwitchAuthError:
            raise
        except TwitchError as error:
            log.warning("não foi possível obter os clips de %s: %s", streamer.twitch, error)
            continue
        for clip in found:
            streamer_of[clip.id] = streamer
        clips.extend(found)

    def reject(clip: Clip) -> None:
        log.info("clip %s ignorado: é de outro jogo ('%s')", clip.id, clip.game_id)
        state.record_skipped(clip, now)

    done_ids = state.done_ids(game_id)
    candidates = eligible(clips, game_id=game_id, cfg=config.selection, done_ids=done_ids)
    chosen = select(
        clips,
        game_id=game_id,
        cfg=config.selection,
        done_ids=done_ids,
        seen_moments=state.delivered_moments(),
        delivered_today=state.delivered_today(now),
        now=now,
        # Só a fonte sem chaves tem de descobrir o jogo clip a clip. Os que
        # afinal são de outro jogo ficam registados, para não voltar a gastar
        # uma consulta com eles na execução seguinte.
        resolve=getattr(twitch, "resolve_game", None),
        on_reject=reject,
    )

    if publisher is None:
        return RunSummary(candidates=len(candidates), delivered=0, failed=0, waiting=len(chosen))

    delivered = failed = 0
    for clip in chosen:
        if out_of_time is not None and out_of_time():
            log.warning("tempo da execução esgotado; os clips restantes ficam para a próxima")
            break
        # A tentativa conta antes de começar: se a execução for morta a meio
        # deste clip, ele não fica a bloquear as seguintes para sempre.
        state.record_failure(clip, now)
        if checkpoint is not None:
            checkpoint()
        try:
            publisher.publish(process(clip, streamer_of[clip.id]))
        except Exception as error:  # um clip falhado não trava os seguintes
            log.warning("clip %s falhou: %s", clip.id, error)
            failed += 1
        else:
            log.info("clip %s entregue (%s)", clip.id, clip.broadcaster_login)
            state.record_delivered(clip, now)
            delivered += 1
        if checkpoint is not None:
            checkpoint()
    return RunSummary(candidates=len(candidates), delivered=delivered, failed=failed)
