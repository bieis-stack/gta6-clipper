"""Entrega dos clips num chat do Telegram, através de um bot."""

from __future__ import annotations

import html
import logging

import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError

from clipper.models import RenderedClip
from clipper.publishers.base import PublishError

log = logging.getLogger(__name__)

API_URL = "https://api.telegram.org"
VIDEO_TIMEOUT = 120
MESSAGE_TIMEOUT = 15


class _OutcomeUnknown(Exception):
    """O pedido saiu mas não houve resposta: o Telegram pode tê-lo cumprido."""


def _never_left(error: requests.RequestException) -> bool:
    """A ligação nem chegou a abrir, logo nada foi enviado?"""
    if isinstance(error, requests.ConnectTimeout):
        return True
    cause = error.args[0] if error.args else None
    return isinstance(cause, MaxRetryError) and isinstance(cause.reason, NewConnectionError)


class TelegramPublisher:
    def __init__(self, token: str, chat_id: str, session: requests.Session | None = None) -> None:
        self._token = token
        self._chat_id = str(chat_id)
        self._session = session or requests.Session()

    def check(self) -> None:
        """Confirma, antes de gastar tempo a editar, que o bot consegue falar com o chat."""
        try:
            self._call("getChat", MESSAGE_TIMEOUT, data={"chat_id": self._chat_id})
        except _OutcomeUnknown as error:
            raise PublishError(f"sem resposta do Telegram: {error}") from None
        except PublishError as error:
            reason = str(error)
            if "401" in reason or "Unauthorized" in reason:
                hint = "o token do bot não é válido; confirma TELEGRAM_BOT_TOKEN"
            elif "403" in reason or "Forbidden" in reason:
                hint = "o bot foi bloqueado ou removido do chat; desbloqueia-o no Telegram"
            else:
                hint = (
                    "o bot não encontra o chat; confirma TELEGRAM_CHAT_ID e que já enviaste "
                    "uma mensagem ao bot"
                )
            raise PublishError(f"Telegram mal configurado: {hint} ({reason})") from None

    def publish(self, item: RenderedClip) -> None:
        if item.cover_path is not None:
            try:
                self._send_cover(item)
            except (PublishError, _OutcomeUnknown) as error:
                # A capa é um extra: sem ela, o vídeo segue na mesma.
                log.warning("capa de %s não enviada: %s", item.clip.id, error)
        uncertain = False
        try:
            self._send_video(item)
        except _OutcomeUnknown as error:
            # Repetir podia duplicar o vídeo no chat: conta como entregue e avisa.
            log.warning("vídeo de %s enviado sem confirmação do Telegram: %s", item.clip.id, error)
            uncertain = True
        try:
            self._send_details(item, uncertain)
        except (PublishError, _OutcomeUnknown) as error:
            # O vídeo já chegou: repetir o envio duplicava-o no chat.
            log.warning("vídeo de %s entregue, mas a descrição falhou: %s", item.clip.id, error)

    def _send_cover(self, item: RenderedClip) -> None:
        try:
            with open(item.cover_path, "rb") as cover:
                self._call(
                    "sendPhoto",
                    MESSAGE_TIMEOUT * 2,
                    data={"chat_id": self._chat_id, "caption": "🖼️ Capa (thumbnail)"},
                    files={"photo": (f"{item.clip.id}.jpg", cover, "image/jpeg")},
                )
        except OSError as error:
            raise PublishError(f"capa de {item.clip.id} ilegível: {error.strerror}") from None

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

    def _send_details(self, item: RenderedClip, uncertain: bool) -> None:
        clip = item.clip
        text = (
            f"<pre>{html.escape(item.description)}</pre>\n"
            f"{html.escape(clip.broadcaster_name)} · {clip.view_count} visualizações na Twitch\n"
            f"{html.escape(clip.url)}"
        )
        if uncertain:
            text += (
                "\n⚠️ O Telegram não confirmou a receção do vídeo deste clip: "
                "pode não ter chegado. Não será reenviado."
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
            summary = f"{type(error).__name__} em {method}"
            if _never_left(error):
                raise PublishError(f"sem ligação ao Telegram: {summary}") from None
            raise _OutcomeUnknown(summary) from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200 or not body.get("ok"):
            reason = body.get("description") or "sem detalhe"
            raise PublishError(f"o Telegram recusou {method} (HTTP {response.status_code}): {reason}")
