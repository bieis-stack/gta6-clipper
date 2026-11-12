"""Entrega dos clips na página Releases do próprio repositório do GitHub.

É o destino usado quando não há bot do Telegram configurado: não precisa de
nenhuma chave, porque o GitHub Actions dá a cada execução um acesso próprio.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import requests

from clipper.models import RenderedClip
from clipper.publishers.base import PublishError

log = logging.getLogger(__name__)

API_URL = "https://api.github.com"
TAG_PREFIX = "clip-"
TIMEOUT = 30
UPLOAD_TIMEOUT = 180
FENCE = "```"


class GitHubReleasePublisher:
    def __init__(self, token: str, repository: str, session: requests.Session | None = None) -> None:
        self._repo_url = f"{API_URL}/repos/{repository}"
        self._session = session or requests.Session()
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def check(self) -> None:
        self._call("GET", self._repo_url, "aceder ao repositório")

    def publish(self, item: RenderedClip) -> None:
        tag = TAG_PREFIX + item.clip.id
        asset = f"{item.clip.id}.mp4"
        release = self._release(tag, item)
        if any(existing.get("name") == asset for existing in release.get("assets") or []):
            return  # tentativa anterior já tinha conseguido: não duplicar
        upload_url = release["upload_url"].split("{")[0]
        try:
            with open(item.video_path, "rb") as video:
                self._call(
                    "POST",
                    upload_url,
                    "anexar o vídeo",
                    timeout=UPLOAD_TIMEOUT,
                    params={"name": asset},
                    headers={"Content-Type": "video/mp4"},
                    data=video,
                )
        except OSError as error:
            raise PublishError(f"vídeo de {item.clip.id} ilegível: {error.strerror}") from None

    def prune(self, now: datetime, days: int = 7) -> None:
        """Apaga as releases de clips antigas, para a página não crescer sem fim."""
        try:
            releases = self._call(
                "GET", f"{self._repo_url}/releases", "listar releases", params={"per_page": 100}
            )
            limit = now - timedelta(days=days)
            for release in releases:
                tag = release.get("tag_name") or ""
                created = datetime.fromisoformat(release["created_at"].replace("Z", "+00:00"))
                if tag.startswith(TAG_PREFIX) and created < limit:
                    self._call("DELETE", f"{self._repo_url}/releases/{release['id']}", "apagar release")
                    self._call("DELETE", f"{self._repo_url}/git/refs/tags/{tag}", "apagar etiqueta")
        except (PublishError, KeyError, TypeError, ValueError) as error:
            log.warning("não foi possível limpar releases antigas: %s", error)

    def _release(self, tag: str, item: RenderedClip) -> dict:
        clip = item.clip
        body = (
            f"**Título**\n\n{FENCE}\n{item.title}\n{FENCE}\n\n"
            f"**Descrição**\n\n{FENCE}\n{item.description}\n{FENCE}\n\n"
            f"{clip.broadcaster_name} · {clip.view_count} visualizações na Twitch · {clip.url}"
        )
        payload = {"tag_name": tag, "name": item.title, "body": body}
        try:
            return self._call("POST", f"{self._repo_url}/releases", "criar a release", json=payload)
        except PublishError as error:
            if "HTTP 422" not in str(error):
                raise
        # 422: a etiqueta já existe, de uma tentativa anterior que ficou a meio.
        return self._call("GET", f"{self._repo_url}/releases/tags/{tag}", "reabrir a release")

    def _call(self, method: str, url: str, action: str, *, timeout: int = TIMEOUT, headers=None, **kwargs):
        try:
            response = self._session.request(
                method, url, headers={**self._headers, **(headers or {})}, timeout=timeout, **kwargs
            )
        except requests.RequestException as error:
            # A mensagem original pode trazer cabeçalhos com o token.
            raise PublishError(f"sem ligação ao GitHub ao {action}: {type(error).__name__}") from None
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}
        if response.status_code >= 300:
            reason = body.get("message") if isinstance(body, dict) else None
            raise PublishError(
                f"o GitHub recusou {action} (HTTP {response.status_code}): {reason or 'sem detalhe'}"
            )
        return body
