import pytest

from clipper import __main__ as cli
from clipper.__main__ import main
from clipper.pipeline import GameNotFound, RunSummary
from clipper.publishers.base import PublishError
from clipper.publishers.github_release import GitHubReleasePublisher
from clipper.publishers.local import LocalPublisher
from clipper.publishers.telegram import TelegramPublisher
from clipper.twitch import TwitchAuthError, TwitchClient
from clipper.twitch_public import PublicTwitch

SECRETS = {
    "TWITCH_CLIENT_ID": "twitch-id-value",
    "TWITCH_CLIENT_SECRET": "twitch-secret-value",
    "TELEGRAM_BOT_TOKEN": "111:telegram-token-value",
    "TELEGRAM_CHAT_ID": "424242",
}


@pytest.fixture
def env(monkeypatch):
    for name in (*SECRETS, "GITHUB_TOKEN", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(name, raising=False)

    def setenv(*names):
        for name in names:
            monkeypatch.setenv(name, SECRETS[name])

    return setenv


@pytest.fixture(autouse=True)
def telegram_check(monkeypatch):
    """Substitui a verificação prévia do Telegram, que faria um pedido real."""
    state = {"calls": 0, "error": None}

    def check(self):
        state["calls"] += 1
        if state["error"]:
            raise state["error"]

    monkeypatch.setattr(TelegramPublisher, "check", check)
    monkeypatch.setattr(GitHubReleasePublisher, "check", check)
    monkeypatch.setattr(GitHubReleasePublisher, "prune", lambda self, now: state.update(pruned=True))
    return state


@pytest.fixture
def paths(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text('game_name: "Grand Theft Auto VI"\nstreamers: [{twitch: shroud}]\n')
    return {"config": config, "state": tmp_path / "state" / "state.json", "out": tmp_path / "out"}


@pytest.fixture
def fake_run(monkeypatch):
    calls = []

    def run(config, state, twitch, publisher, *, now, process, checkpoint=None, out_of_time=None):
        calls.append(
            {"config": config, "publisher": publisher, "checkpoint": checkpoint,
             "out_of_time": out_of_time, "twitch": twitch}
        )
        if run.error:
            raise run.error
        return run.summary

    run.error = None
    run.summary = RunSummary(candidates=3, delivered=2, failed=1)
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


def test_telegram_is_checked_before_any_work(env, paths, fake_run, telegram_check, capsys):
    env(*SECRETS)
    telegram_check["error"] = PublishError("Telegram mal configurado: confirma TELEGRAM_CHAT_ID")
    assert main(argv(paths)) == 1
    assert fake_run.calls == []
    assert "TELEGRAM_CHAT_ID" in capsys.readouterr().err


def test_dry_run_does_not_check_telegram(env, paths, fake_run, telegram_check):
    env("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET")
    main(argv(paths, "--dry-run"))
    assert telegram_check["calls"] == 0


def test_run_where_every_clip_failed_exits_1_but_keeps_state(env, paths, fake_run, capsys):
    env(*SECRETS)
    fake_run.summary = RunSummary(candidates=2, delivered=0, failed=2)
    assert main(argv(paths)) == 1
    assert paths["state"].exists()
    captured = capsys.readouterr()
    assert "candidatos=2 entregues=0 falhados=2" in captured.out
    assert "nenhum clip" in captured.err


def test_run_with_some_failures_but_deliveries_stays_green(env, paths, fake_run):
    env(*SECRETS)
    fake_run.summary = RunSummary(candidates=3, delivered=1, failed=1)
    assert main(argv(paths)) == 0


def test_time_budget_is_passed_to_the_run(env, paths, fake_run, monkeypatch):
    env(*SECRETS)
    clock = {"now": 1000.0}
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock["now"])
    main(argv(paths))
    out_of_time = fake_run.calls[0]["out_of_time"]
    assert out_of_time() is False
    clock["now"] += cli.RUN_BUDGET_SECONDS + 1
    assert out_of_time() is True


# --- sem chaves: fonte pública da Twitch e entrega em Releases ---


def test_with_twitch_keys_the_official_api_is_used(env, paths, fake_run):
    env(*SECRETS)
    main(argv(paths))
    assert isinstance(fake_run.calls[0]["twitch"], TwitchClient)


def test_without_twitch_keys_the_public_listing_is_used(env, paths, fake_run):
    env("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    assert main(argv(paths)) == 0
    assert isinstance(fake_run.calls[0]["twitch"], PublicTwitch)


def test_without_telegram_keys_clips_go_to_github_releases(env, paths, fake_run, monkeypatch, telegram_check):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_value")
    monkeypatch.setenv("GITHUB_REPOSITORY", "bieis-stack/gta6-clipper")
    assert main(argv(paths)) == 0
    assert isinstance(fake_run.calls[0]["publisher"], GitHubReleasePublisher)
    assert telegram_check["calls"] == 1  # o destino é verificado antes de trabalhar
    assert telegram_check.get("pruned") is True


def test_telegram_wins_over_github_releases_when_configured(env, paths, fake_run, monkeypatch):
    env("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_value")
    monkeypatch.setenv("GITHUB_REPOSITORY", "bieis-stack/gta6-clipper")
    main(argv(paths))
    assert isinstance(fake_run.calls[0]["publisher"], TelegramPublisher)


def test_no_destination_at_all_is_an_error_that_says_what_to_do(env, paths, fake_run, capsys):
    assert main(argv(paths)) == 1
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err
    assert fake_run.calls == []


@pytest.mark.parametrize(
    "present, missing",
    [("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"), ("TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN")],
)
def test_half_configured_pair_is_an_error_naming_the_missing_half(env, paths, fake_run, present, missing, capsys):
    env(present)
    assert main(argv(paths, "--dry-run")) == 1 if present.startswith("TWITCH") else main(argv(paths)) == 1
    assert missing in capsys.readouterr().err
