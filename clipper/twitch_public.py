"""Clips da Twitch sem chaves, a partir das páginas públicas (via yt-dlp).

Tem a mesma interface do TwitchClient, para o resto do sistema não distinguir
as duas fontes. A diferença é que a listagem pública não diz de que jogo é
cada clip: isso descobre-se depois, um clip de cada vez, com `resolve_game`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import yt_dlp

from clipper.models import Clip
from clipper.twitch import TwitchError, User

log = logging.getLogger(__name__)

CLIPS_PER_CHANNEL = 50
LISTING_ATTEMPTS = 3
RETRY_PAUSE = 2  # segundos
_OPTIONS = {"quiet": True, "no_warnings": True, "noprogress": True, "socket_timeout": 30}


def _normalise(name: str) -> str:
    return name.strip().casefold()


class PublicTwitch:
    def get_game_id(self, name: str) -> str:
        return _normalise(name)

    def get_users(self, logins: list[str]) -> dict[str, User]:
        # Não há como confirmar aqui que o canal existe; se não existir, a
        # listagem dos clips falha e esse streamer é ignorado com um aviso.
        return {login.lower(): User(login.lower(), login.lower(), login.lower()) for login in logins}

    def get_clips(self, user: User, started_at: datetime, ended_at: datetime) -> list[Clip]:
        span = "24hr" if ended_at - started_at <= timedelta(hours=24) else "7d"
        url = f"https://www.twitch.tv/{user.login}/clips?range={span}"
        options = {**_OPTIONS, "extract_flat": True, "playlistend": CLIPS_PER_CHANNEL}
        # A página pública devolve às vezes uma lista vazia a um canal que tem
        # dezenas de clips; repetir resolve quase sempre.
        for attempt in range(LISTING_ATTEMPTS):
            if attempt:
                time.sleep(RETRY_PAUSE)
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=False) or {}
            except Exception as error:
                raise TwitchError(f"não foi possível listar os clips de {user.login}: {error}") from None
            entries = list(info.get("entries") or [])
            if entries:
                break
        clips = (self._clip(entry, user) for entry in entries)
        return [clip for clip in clips if clip and started_at <= clip.created_at <= ended_at]

    @staticmethod
    def _clip(entry, user: User) -> Clip | None:
        try:
            url = entry["url"]
            return Clip(
                id=url.rstrip("/").rsplit("/", 1)[-1].split("?")[0],
                url=url,
                broadcaster_id=user.id,
                broadcaster_login=user.login,
                broadcaster_name=user.display_name,
                title=entry.get("title") or "",
                game_id=None,
                view_count=int(entry.get("view_count") or 0),
                created_at=datetime.fromtimestamp(int(entry["timestamp"]), UTC),
                duration=float(entry.get("duration") or 0),
                video_id=None,
                vod_offset=None,
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            return None

    def resolve_game(self, clip: Clip) -> Clip | None:
        """O mesmo clip, já com o jogo e o nome do canal. None se a consulta falhar."""
        try:
            with yt_dlp.YoutubeDL(dict(_OPTIONS)) as ydl:
                info = ydl.extract_info(clip.url, download=False) or {}
        except Exception as error:
            log.warning("não foi possível saber o jogo do clip %s: %s", clip.id, error)
            return None
        categories = info.get("categories") or []
        return replace(
            clip,
            game_id=_normalise(categories[0]) if categories else "",
            broadcaster_name=info.get("channel") or clip.broadcaster_name,
        )
