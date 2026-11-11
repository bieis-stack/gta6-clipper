import pytest

from clipper import __main__ as cli
from clipper.__main__ import main
from clipper.pipeline import GameNotFound, RunSummary
from clipper.publishers.local import LocalPublisher
from clipper.publishers.telegram import TelegramPublisher
from clipper.twitch import TwitchAuthError

SECRETS = {
    "TWITCH_CLIENT_ID": "twitch-id-value",
    "TWITCH_CLIENT_SECRET": "twitch-secret-value",
    "TELEGRAM_BOT_TOKEN": "111:telegram-token-value",
    "TELEGRAM_CHAT_ID": "424242",
}


@pytest.fixture
def env(monkeypatch):
    for name in SECRETS:
        monkeypatch.delenv(name, raising=False)

    def setenv(*names):
        for name in names:
            monkeypatch.setenv(name, SECRETS[name])

    return setenv


@pytest.fixture
def paths(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text('game_name: "Grand Theft Auto VI"\nstreamers: [{twitch: shroud}]\n')
    return {"config": config, "state": tmp_path / "state" / "state.json", "out": tmp_path / "out"}


@pytest.fixture
def fake_run(monkeypatch):
    calls = []

    def run(config, state, twitch, publisher, *, now, process, checkpoint=None):
        calls.append({"config": config, "publisher": publisher, "checkpoint": checkpoint})
        if run.error:
            raise run.error
        return RunSummary(candidates=3, delivered=2, failed=1)

    run.error = None
    run.calls = calls
    monkeypatch.setattr(cli, "run", run)
    return run


def argv(paths, *extra):
    return [
        "run", "--config", str(paths["config"]), "--state", str(paths["state"]),
        "--out", str(paths["out"]), *extra,
    ]


def test_missing_config_returns_1(tmp_path, env, capsys):
    env(*SECRETS)
    assert main(["run", "--config", str(tmp_path / "nope.yaml")]) == 1
    assert "nope.yaml" in capsys.readouterr().err


def test_missing_env_var_is_named(env, paths, fake_run, capsys):
    env("TWITCH_CLIENT_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    assert main(argv(paths)) == 1
    assert "TWITCH_CLIENT_SECRET" in capsys.readouterr().err
    assert fake_run.calls == []


def test_dry_run_does_not_need_telegram_vars_nor_touch_state(env, paths, fake_run):
    env("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET")
    assert main(argv(paths, "--dry-run")) == 0
    assert isinstance(fake_run.calls[0]["publisher"], LocalPublisher)
    assert fake_run.calls[0]["checkpoint"] is None
    assert not paths["state"].exists()


def test_normal_run_saves_state_and_prints_summary(env, paths, fake_run, capsys):
    env(*SECRETS)
    assert main(argv(paths)) == 0
    assert isinstance(fake_run.calls[0]["publisher"], TelegramPublisher)
    assert paths["state"].exists()
    assert "candidatos=3 entregues=2 falhados=1" in capsys.readouterr().out


def test_normal_run_checkpoint_saves_state(env, paths, fake_run):
    env(*SECRETS)
    main(argv(paths))
    paths["state"].unlink()
    fake_run.calls[0]["checkpoint"]()
    assert paths["state"].exists()


def test_game_name_option_overrides_config(env, paths, fake_run):
    env(*SECRETS)
    assert main(argv(paths, "--game-name", "Grand Theft Auto V")) == 0
    assert fake_run.calls[0]["config"].game_name == "Grand Theft Auto V"


def test_empty_game_name_option_keeps_config(env, paths, fake_run):
    env(*SECRETS)
    assert main(argv(paths, "--game-name", "")) == 0
    assert fake_run.calls[0]["config"].game_name == "Grand Theft Auto VI"


def test_corrupt_state_returns_1(env, paths, fake_run, capsys):
    env(*SECRETS)
    paths["state"].parent.mkdir(parents=True)
    paths["state"].write_text("{")
    assert main(argv(paths)) == 1
    assert fake_run.calls == []
    assert "estado" in capsys.readouterr().err


@pytest.mark.parametrize("error", [TwitchAuthError("credenciais recusadas"), GameNotFound("jogo")])
def test_global_errors_return_1(env, paths, fake_run, error, capsys):
    env(*SECRETS)
    fake_run.error = error
    assert main(argv(paths)) == 1
    assert str(error) in capsys.readouterr().err


def test_secret_values_never_printed(env, paths, fake_run, capsys):
    env(*SECRETS)
    fake_run.error = TwitchAuthError("credenciais recusadas")
    main(argv(paths))
    main(argv(paths, "--dry-run"))
    output = capsys.readouterr()
    for value in SECRETS.values():
        assert value not in output.out + output.err
