"""Linha de comandos: python -m clipper run"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from clipper.config import ConfigError, load_config
from clipper.pipeline import GameNotFound, process_clip, run
from clipper.publishers.local import LocalPublisher
from clipper.publishers.telegram import TelegramPublisher
from clipper.state import State, StateError
from clipper.twitch import TwitchClient, TwitchError

ASSETS = Path(__file__).resolve().parent.parent / "assets"


class MissingSecret(Exception):
    pass


def _secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingSecret(f"falta a variável de ambiente {name}")
    return value


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
    twitch = TwitchClient(_secret("TWITCH_CLIENT_ID"), _secret("TWITCH_CLIENT_SECRET"))
    if args.dry_run:
        publisher = LocalPublisher(args.out)
        checkpoint = None
    else:
        publisher = TelegramPublisher(_secret("TELEGRAM_BOT_TOKEN"), _secret("TELEGRAM_CHAT_ID"))
        checkpoint = lambda: state.save(args.state)  # noqa: E731
    state = State.load(args.state)

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
        )
    if not args.dry_run:
        state.save(args.state)
    print(
        f"candidatos={summary.candidates} entregues={summary.delivered} falhados={summary.failed}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        return _run(args)
    except (ConfigError, StateError, MissingSecret, GameNotFound, TwitchError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
