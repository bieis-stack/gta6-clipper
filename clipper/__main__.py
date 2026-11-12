"""Linha de comandos: python -m clipper run"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from clipper.config import ConfigError, load_config
from clipper.pipeline import GameNotFound, process_clip, run
from clipper.publishers.base import PublishError
from clipper.publishers.github_release import GitHubReleasePublisher
from clipper.publishers.local import LocalPublisher
from clipper.publishers.telegram import TelegramPublisher
from clipper.state import State, StateError
from clipper.twitch import TwitchClient, TwitchError
from clipper.twitch_public import PublicTwitch

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parent.parent / "assets"
# O trabalho no GitHub Actions é morto aos 14 minutos; deixar de começar clips
# aos 8 dá margem para acabar o que estiver em curso e gravar o estado.
RUN_BUDGET_SECONDS = 8 * 60


class MissingSecret(Exception):
    pass


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _pair(first: str, second: str) -> tuple[str, str] | None:
    """Duas chaves que só fazem sentido juntas. None se nenhuma estiver definida."""
    a, b = _env(first), _env(second)
    if a and b:
        return a, b
    if a or b:
        raise MissingSecret(f"falta a variável de ambiente {second if a else first}")
    return None


def _source():
    keys = _pair("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET")
    if keys:
        log.info("fonte: API oficial da Twitch")
        return TwitchClient(*keys)
    log.info("fonte: páginas públicas da Twitch (sem chaves)")
    return PublicTwitch()


def _destination():
    telegram = _pair("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    if telegram:
        log.info("destino: Telegram")
        return TelegramPublisher(*telegram)
    token, repository = _env("GITHUB_TOKEN"), _env("GITHUB_REPOSITORY")
    if token and repository:
        log.info("destino: página Releases de %s", repository)
        return GitHubReleasePublisher(token, repository)
    raise MissingSecret(
        "não há para onde enviar os clips: define TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID "
        "(ou corre no GitHub Actions, que os publica na página Releases)"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipper", description="Clips da Twitch para o Telegram")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="procura, edita e entrega clips novos")
    run_parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    run_parser.add_argument("--state", type=Path, default=Path("state/state.json"))
    run_parser.add_argument("--game-name", default="", help="substitui o game_name da configuração")
    run_parser.add_argument(
        "--dry-run", action="store_true", help="grava os vídeos em --out; não envia nem altera o estado"
    )
    run_parser.add_argument("--out", type=Path, default=Path("out"))
    run_parser.add_argument("--work", type=Path, default=None, help="pasta de trabalho a conservar")
    return parser


def _run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.game_name.strip():
        config = replace(config, game_name=args.game_name.strip())
    twitch = _source()
    if args.dry_run:
        publisher = LocalPublisher(args.out)
        checkpoint = None
    else:
        publisher = _destination()
        checkpoint = lambda: state.save(args.state)  # noqa: E731
    state = State.load(args.state)
    if not args.dry_run:
        publisher.check()
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="clipper-") as temporary:
        work_dir = args.work or Path(temporary)
        process = partial(process_clip, config=config, work_dir=work_dir, assets_dir=ASSETS)
        summary = run(
            config,
            state,
            twitch,
            publisher,
            now=datetime.now(UTC),
            process=process,
            checkpoint=checkpoint,
            out_of_time=lambda: time.monotonic() - started > RUN_BUDGET_SECONDS,
        )
    if not args.dry_run:
        state.save(args.state)
    if isinstance(publisher, GitHubReleasePublisher):
        publisher.prune(datetime.now(UTC))
    print(
        f"candidatos={summary.candidates} entregues={summary.delivered} falhados={summary.failed}"
    )
    if summary.failed and not summary.delivered:
        # Sem isto, uma avaria total (download bloqueado, ffmpeg em falta) passava
        # despercebida: as execuções ficavam verdes e o Telegram apenas em silêncio.
        print("erro: nenhum clip foi entregue e houve falhas; vê os avisos acima", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # As bibliotecas de rede registam cada pedido; isso esconde as linhas úteis.
    for noisy in ("httpx", "huggingface_hub", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        return _run(args)
    except (
        ConfigError, StateError, MissingSecret, GameNotFound, TwitchError, PublishError
    ) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
