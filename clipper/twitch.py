"""Cliente mínimo da API Helix da Twitch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import requests

from clipper.models import Clip

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.twitch.tv/helix"
TIMEOUT = 15
MAX_PAGES = 3


class TwitchError(Exception):
    pass


class TwitchAuthError(TwitchError):
    pass


@dataclass(frozen=True)
class User:
    id: str
    login: str
    display_name: str


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class TwitchClient:
    def __init__(
        self, client_id: str, client_secret: str, session: requests.Session | None = None
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session or requests.Session()
        self._token: str | None = None

    def get_game_id(self, name: str) -> str | None:
        data = self._get("/games", {"name": name})["data"]
        return data[0]["id"] if data else None

    def get_users(self, logins: list[str]) -> dict[str, User]:
        if not logins:
            return {}
        data = self._get("/users", {"login": [login.lower() for login in logins]})["data"]
        return {
            raw["login"].lower(): User(raw["id"], raw["login"].lower(), raw["display_name"])
            for raw in data
        }

    def get_clips(self, user: User, started_at: datetime, ended_at: datetime) -> list[Clip]:
        params = {
            "broadcaster_id": user.id,
            "started_at": _rfc3339(started_at),
            "ended_at": _rfc3339(ended_at),
            "first": "100",
        }
        clips: list[Clip] = []
        for _ in range(MAX_PAGES):
            body = self._get("/clips", params)
            clips.extend(self._clip(raw, user) for raw in body["data"])
            cursor = (body.get("pagination") or {}).get("cursor")
            if not cursor:
                break
            params = {**params, "after": cursor}
        return clips

    @staticmethod
    def _clip(raw: dict, user: User) -> Clip:
        return Clip(
            id=raw["id"],
            url=raw["url"],
            broadcaster_id=raw["broadcaster_id"],
            broadcaster_login=user.login,
            broadcaster_name=raw.get("broadcaster_name") or user.display_name,
            title=raw.get("title") or "",
            game_id=raw.get("game_id") or "",
            view_count=int(raw.get("view_count") or 0),
            created_at=datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00")),
            duration=float(raw.get("duration") or 0),
            video_id=raw.get("video_id") or None,
            vod_offset=raw.get("vod_offset"),
        )

    def _authenticate(self) -> str:
        try:
            response = self._session.post(
                TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException as error:
            raise TwitchError(f"sem ligação à Twitch: {type(error).__name__}") from None
        if response.status_code != 200:
            raise TwitchAuthError(
                f"a Twitch recusou as credenciais (HTTP {response.status_code}); "
                "confirma TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET"
            )
        return response.json()["access_token"]

    def _get(self, path: str, params: dict) -> dict:
        if self._token is None:
            self._token = self._authenticate()
        headers = {"Client-Id": self._client_id, "Authorization": f"Bearer {self._token}"}
        try:
            response = self._session.get(
                API_URL + path, params=params, headers=headers, timeout=TIMEOUT
            )
        except requests.RequestException as error:
            raise TwitchError(f"sem ligação à Twitch em {path}: {type(error).__name__}") from None
        if response.status_code == 401:
            raise TwitchAuthError(f"a Twitch rejeitou o acesso em {path} (HTTP 401)")
        if response.status_code != 200:
            raise TwitchError(f"erro da Twitch em {path} (HTTP {response.status_code})")
        try:
            return response.json()
        except ValueError:
            raise TwitchError(f"resposta inesperada da Twitch em {path}") from None
