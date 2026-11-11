"""Entrega dos clips num chat do Telegram, através de um bot."""

from __future__ import annotations

import html
import logging

import requests

from clipper.models import RenderedClip
from clipper.publishers.base import PublishError

log = logging.getLogger(__name__)

API_URL = "https://api.telegram.org"
VIDEO_TIMEOUT = 120
MESSAGE_TIMEOUT = 15


class TelegramPublisher:
    def __init__(self, token: str, chat_id: str, session: requests.Session | None = None) -> None:
        self._token = token
        self._chat_id = str(chat_id)
        self._session = session or requests.Session()

    def publish(self, item: RenderedClip) -> None:
        self._send_video(item)
        try:
            self._send_details(item)
        except PublishError as error:
            # O vídeo já chegou: repetir o envio duplicava-o no chat.
            log.warning("vídeo de %s entregue, mas a descrição falhou: %s", item.clip.id, error)

    def _send_video(self, item: RenderedClip) -> None:
        try:
            with open(item.video_path, "rb") as video:
                self._call(
                    "sendVideo",
                    VIDEO_TIMEOUT,
                    data={
                        "chat_id": self._chat_id,
                        "caption": item.title,
                        "supports_streaming": "true",
                        "width": "1080",
                        "height": "1920",
                    },
                    files={"video": (f"{item.clip.id}.mp4", video, "video/mp4")},
                )
        except OSError as error:
            raise PublishError(f"vídeo de {item.clip.id} ilegível: {error.strerror}") from None

    def _send_details(self, item: RenderedClip) -> None:
        clip = item.clip
        text = (
            f"<pre>{html.escape(item.description)}</pre>\n"
            f"{html.escape(clip.broadcaster_name)} · {clip.view_count} visualizações na Twitch\n"
            f"{html.escape(clip.url)}"
        )
        self._call(
            "sendMessage",
            MESSAGE_TIMEOUT,
            data={
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )

    def _call(self, method: str, timeout: int, **kwargs) -> None:
        url = f"{API_URL}/bot{self._token}/{method}"
        try:
            response = self._session.post(url, timeout=timeout, **kwargs)
        except requests.RequestException as error:
            # A mensagem original pode conter o URL, que inclui o token do bot.
            raise PublishError(f"sem ligação ao Telegram em {method}: {type(error).__name__}") from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200 or not body.get("ok"):
            reason = body.get("description") or f"HTTP {response.status_code}"
            raise PublishError(f"o Telegram recusou {method}: {reason}")
