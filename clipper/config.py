"""Leitura e validação do config.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from pathlib import Path

import yaml

from clipper.models import Rect, Streamer

DEFAULT_HASHTAGS = ("#GTA6", "#GTAVI", "#shorts")
_CHANNEL_LINK = re.compile(r"^(https?://)?(www\.|m\.)?twitch\.tv/")
_LOGIN = re.compile(r"[a-z0-9_]{1,25}")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class SelectionConfig:
    lookback_hours: int = 6
    min_views: int = 30
    min_duration: float = 15
    max_duration: float = 60
    max_per_run: int = 2
    max_per_day: int = 5


@dataclass(frozen=True)
class HookConfig:
    enabled: bool = True
    seconds: float = 1.5  # duração do flash-forward; 0 desliga só o flash-forward
    model: str = "gemini-flash-latest"


@dataclass(frozen=True)
class Config:
    game_name: str
    streamers: tuple[Streamer, ...]
    selection: SelectionConfig
    hashtags: tuple[str, ...]
    hook: HookConfig = HookConfig()


def _mapping(value, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"config: '{where}' tem de ser um conjunto de chaves e valores")
    return value


def _reject_unknown(data: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(map(str, data)) - allowed)
    if unknown:
        raise ConfigError(f"config: chave desconhecida em {where}: {', '.join(unknown)}")


def _number(value, name: str, *, integer: bool = False) -> float:
    kinds = (int,) if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, kinds) or value < 0:
        raise ConfigError(f"config: '{name}' tem de ser um número não negativo")
    return value


def _facecam(raw, login: str) -> Rect | None:
    if raw is None:
        return None
    data = _mapping(raw, f"facecam de {login}")
    _reject_unknown(data, {"x", "y", "w", "h"}, f"facecam de {login}")
    try:
        rect = Rect(*(int(data[key]) for key in ("x", "y", "w", "h")))
    except (KeyError, TypeError, ValueError):
        raise ConfigError(f"config: facecam de {login} precisa de x, y, w e h inteiros") from None
    if rect.x < 0 or rect.y < 0 or rect.w <= 0 or rect.h <= 0:
        raise ConfigError(f"config: facecam de {login} tem dimensões inválidas")
    return rect


def _login(raw) -> str:
    """Nome do canal da Twitch, aceitando também a ligação do canal ou um @nome."""
    written = str(raw or "").strip()
    if not written:
        raise ConfigError("config: cada streamer precisa do campo 'twitch'")
    login = _CHANNEL_LINK.sub("", written.lower()).lstrip("@")
    login = login.split("?")[0].split("/")[0]
    if not _LOGIN.fullmatch(login):
        raise ConfigError(
            f"config: '{written}' não é um canal da Twitch válido no campo 'twitch'; "
            "usa só o nome do canal, como aparece em twitch.tv/nome"
        )
    return login


def _streamers(raw) -> tuple[Streamer, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError("config: 'streamers' tem de ser uma lista")
    result = []
    for entry in raw:
        data = _mapping(entry, "streamers")
        _reject_unknown(data, {"twitch", "facecam"}, "streamers")
        login = _login(data.get("twitch"))
        result.append(Streamer(login, _facecam(data.get("facecam"), login)))
    return tuple(result)


def _selection(raw) -> SelectionConfig:
    data = _mapping(raw, "selection")
    names = {field.name for field in fields(SelectionConfig)}
    _reject_unknown(data, names, "selection")
    integers = {"lookback_hours", "min_views", "max_per_run", "max_per_day"}
    values = {name: _number(value, name, integer=name in integers) for name, value in data.items()}
    selection = SelectionConfig(**values)
    if selection.min_duration > selection.max_duration:
        raise ConfigError("config: min_duration não pode ser maior do que max_duration")
    return selection


def _hashtags(raw) -> tuple[str, ...]:
    data = _mapping(raw, "metadata")
    _reject_unknown(data, {"hashtags"}, "metadata")
    tags = data.get("hashtags")
    if tags is None:
        return DEFAULT_HASHTAGS
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ConfigError("config: 'hashtags' tem de ser uma lista de textos")
    return tuple(tags)


def _hook(raw) -> HookConfig:
    data = _mapping(raw, "hook")
    _reject_unknown(data, {"enabled", "seconds", "model"}, "hook")
    defaults = HookConfig()
    enabled = data.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        raise ConfigError("config: 'enabled' em hook tem de ser true ou false")
    seconds = _number(data.get("seconds", defaults.seconds), "seconds")
    if seconds > 5:
        raise ConfigError("config: 'seconds' em hook não pode passar de 5")
    model = data.get("model", defaults.model)
    if not isinstance(model, str) or not model.strip():
        raise ConfigError("config: 'model' em hook tem de ser o nome de um modelo do Gemini")
    return HookConfig(enabled=enabled, seconds=seconds, model=model.strip())


def load_config(path: Path) -> Config:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"config: não foi possível ler {path}: {error.strerror}") from None
    except yaml.YAMLError as error:
        raise ConfigError(f"config: YAML inválido em {path}: {error}") from None
    if not isinstance(raw, dict):
        raise ConfigError("config: o ficheiro tem de ser um conjunto de chaves e valores")
    _reject_unknown(raw, {"game_name", "streamers", "selection", "metadata", "hook"}, "raiz")
    game_name = raw.get("game_name")
    if not isinstance(game_name, str) or not game_name.strip():
        raise ConfigError("config: falta 'game_name'")
    return Config(
        game_name=game_name.strip(),
        streamers=_streamers(raw.get("streamers")),
        selection=_selection(raw.get("selection")),
        hashtags=_hashtags(raw.get("metadata")),
        hook=_hook(raw.get("hook")),
    )
