"""Registo dos clips já tratados e da contagem diária."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clipper.models import Clip, Moment

VERSION = 1
MAX_ATTEMPTS = 3


class StateError(Exception):
    pass


class State:
    def __init__(self, clips: dict[str, dict] | None = None) -> None:
        self._clips: dict[str, dict] = clips or {}

    @classmethod
    def load(cls, path: Path) -> State:
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise StateError(f"estado ilegível em {path}: {error}") from None
        if (
            not isinstance(data, dict)
            or data.get("version") != VERSION
            or not isinstance(data.get("clips"), dict)
        ):
            raise StateError(f"estado com formato inesperado em {path}")
        return cls(data["clips"])

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": VERSION, "clips": self._clips}
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def done_ids(self) -> set[str]:
        return {
            clip_id
            for clip_id, entry in self._clips.items()
            if entry["status"] in ("delivered", "failed", "skipped")
        }

    def delivered_moments(self) -> list[Moment]:
        return [
            Moment(
                entry["broadcaster_id"],
                entry["video_id"],
                entry["vod_offset"],
                datetime.fromisoformat(entry["created_at"]),
            )
            for entry in self._clips.values()
            if entry["status"] == "delivered"
        ]

    def delivered_today(self, now: datetime) -> int:
        today = now.astimezone(UTC).date()
        return sum(
            1
            for entry in self._clips.values()
            if entry["status"] == "delivered"
            and datetime.fromisoformat(entry["updated_at"]).astimezone(UTC).date() == today
        )

    def record_delivered(self, clip: Clip, now: datetime) -> None:
        self._entry(clip, now)["status"] = "delivered"

    def record_failure(self, clip: Clip, now: datetime) -> None:
        entry = self._entry(clip, now)
        entry["attempts"] += 1
        entry["status"] = "failed" if entry["attempts"] >= MAX_ATTEMPTS else "retry"

    def record_skipped(self, clip: Clip, now: datetime) -> None:
        """Clip que não interessa (por exemplo, de outro jogo): não voltar a olhar para ele."""
        self._entry(clip, now)["status"] = "skipped"

    def prune(self, now: datetime, days: int = 14) -> None:
        limit = now - timedelta(days=days)
        self._clips = {
            clip_id: entry
            for clip_id, entry in self._clips.items()
            if datetime.fromisoformat(entry["updated_at"]) >= limit
        }

    def _entry(self, clip: Clip, now: datetime) -> dict:
        entry = self._clips.setdefault(
            clip.id,
            {
                "broadcaster_id": clip.broadcaster_id,
                "video_id": clip.video_id,
                "vod_offset": clip.vod_offset,
                "created_at": clip.created_at.isoformat(),
                "status": "retry",
                "attempts": 0,
            },
        )
        entry["updated_at"] = now.isoformat()
        return entry
