"""Interface comum a todos os destinos de publicação."""

from __future__ import annotations

from typing import Protocol

from clipper.models import RenderedClip


class PublishError(Exception):
    pass


class Publisher(Protocol):
    def publish(self, item: RenderedClip) -> None:
        """Entrega o clip. Lança PublishError se o vídeo não chegar ao destino."""
