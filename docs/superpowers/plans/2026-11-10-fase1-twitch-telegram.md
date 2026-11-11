# Clipper GTA VI — Fase 1 (Twitch → edição → Telegram) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar no Telegram, sem custos e sem intervenção, clips verticais editados de GTA VI obtidos da Twitch, prontos a publicar à mão.

**Architecture:** Pacote Python `clipper` com uma unidade por responsabilidade (configuração, Twitch, seleção, estado, download, facecam, legendas, montagem, textos, publicação) e um orquestrador. Corre no GitHub Actions de 15 em 15 minutos; o estado é um JSON guardado por commit no próprio repositório.

**Tech Stack:** Python 3.12, requests, PyYAML, yt-dlp, faster-whisper, opencv-python-headless, ffmpeg/ffprobe, pytest, responses, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-10-fase1-twitch-telegram-design.md`

## Global Constraints

- Python ≥ 3.11. Só bibliotecas de código aberto e serviços gratuitos.
- Vídeo final: MP4 H.264 + AAC, 1080×1920, `fps = min(fps da origem, 60)`, ≤ 50 MB.
- Todos os instantes são `datetime` com fuso UTC; `now` é sempre injetado, nunca lido dentro das funções puras.
- Segredos só por variáveis de ambiente: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Nunca escritos em registos nem em ficheiros.
- Valores por omissão: `lookback_hours=6`, `min_views=30`, `min_duration=15`, `max_duration=60`, `max_per_run=2`, `max_per_day=5`, hashtags `#GTA6 #GTAVI #shorts`.
- Identificadores do código em inglês; `README` e mensagens de registo em português.
- Cada commit termina com as linhas de atribuição da sessão.

## Review Focus

1. **Título do clip com caracteres especiais** (`{`, `}`, `\`, quebras de linha, emoji, `:` e `'`): o vídeo sai com o texto legível e o `ffmpeg` não falha. → Tasks 9 e 10.
2. **Vídeo de origem fora do padrão** (720p, 4:3, vertical, sem faixa de áudio): a saída é sempre 1080×1920 e reproduzível. → Task 10.
3. **Clip sem VOD** (`video_id: ""`, `vod_offset: null`): a deteção de repetidos usa a hora de criação e nada rebenta. → Tasks 4 e 5.
4. **Ficheiro de estado corrompido ou vazio**: a execução para com erro em vez de reenviar clips antigos. → Tasks 3 e 13.
5. **Falha a meio da entrega** (vídeo enviado, segunda mensagem falha; ou envio do vídeo falha): sem vídeos duplicados no Telegram e sem gastar a quota diária com falhas. → Tasks 11 e 12.

---

## File Structure

| Ficheiro | Responsabilidade |
|---|---|
| `pyproject.toml`, `.gitignore` | Dependências e empacotamento |
| `config.yaml` | Configuração do utilizador |
| `clipper/models.py` | Tipos partilhados: `Rect`, `Streamer`, `Clip`, `Moment`, `RenderedClip` |
| `clipper/config.py` | Ler e validar `config.yaml` |
| `clipper/state.py` | Clips tratados e contagem diária |
| `clipper/selection.py` | Filtrar, remover repetidos, ordenar |
| `clipper/twitch.py` | Cliente da API Helix |
| `clipper/metadata.py` | Título e descrição |
| `clipper/media.py` | `ffprobe` |
| `clipper/download.py` | Download com `yt-dlp` |
| `clipper/facecam.py` | Deteção da zona da facecam |
| `clipper/captions.py` | Transcrição e ficheiro ASS |
| `clipper/layout.py` | Montagem 9:16 com `ffmpeg` |
| `clipper/publishers/{base,local,telegram}.py` | Entrega |
| `clipper/pipeline.py` | Orquestração |
| `clipper/__main__.py` | Linha de comandos |
| `assets/fonts/Anton-Regular.ttf`, `assets/fonts/OFL.txt` | Tipo de letra |
| `assets/models/face_detection_yunet_2023mar.onnx` | Detetor de rostos |
| `.github/workflows/clipper.yml`, `.github/workflows/probe.yml` | Execução agendada e sondagem |
| `tests/test_*.py` | Um ficheiro de testes por unidade |

---

### Task 1: Estrutura do projeto, tipos e configuração

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config.yaml`, `clipper/__init__.py`, `clipper/models.py`, `clipper/config.py`, `tests/helpers.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces (em `clipper/models.py`, todos `@dataclass(frozen=True)`):
  - `Rect(x: int, y: int, w: int, h: int)`
  - `Streamer(twitch: str, facecam: Rect | None = None)`
  - `Clip(id: str, url: str, broadcaster_id: str, broadcaster_login: str, broadcaster_name: str, title: str, game_id: str, view_count: int, created_at: datetime, duration: float, video_id: str | None, vod_offset: int | None)`
  - `Moment(broadcaster_id: str, video_id: str | None, vod_offset: int | None, created_at: datetime)` e `Clip.moment -> Moment` (propriedade)
  - `RenderedClip(clip: Clip, video_path: Path, title: str, description: str)`
- Produces (em `clipper/config.py`):
  - `SelectionConfig(lookback_hours: int = 6, min_views: int = 30, min_duration: float = 15, max_duration: float = 60, max_per_run: int = 2, max_per_day: int = 5)`
  - `Config(game_name: str, streamers: tuple[Streamer, ...], selection: SelectionConfig, hashtags: tuple[str, ...])`
  - `load_config(path: Path) -> Config`, `class ConfigError(Exception)`
- Produces (em `tests/helpers.py`, usado pelos testes das tasks seguintes):
  - `NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)`, `T0 = NOW - timedelta(hours=3)`, `HOUR = timedelta(hours=1)`
  - `clip(id="Abc", *, game="123", duration=30.0, views=100, created=T0, video=<"v-" + id>, offset=0, broadcaster="1", login="shroud", name="Shroud", title="wow") -> Clip`, com `url = "https://clips.twitch.tv/" + id`
  - `m(*, video="v1", offset=0, created=T0, broadcaster="1") -> Moment`

- [ ] **Step 1: Criar `pyproject.toml` e `.gitignore`**

`pyproject.toml`: projeto `clipper`, `requires-python = ">=3.11"`, dependências `requests`, `pyyaml`, `yt-dlp`, `faster-whisper`, `opencv-python-headless`, `numpy`; extra `dev` com `pytest` e `responses`; pacotes `clipper` e `clipper.publishers`.
`.gitignore`: `__pycache__/`, `.venv/`, `out/`, `work/`, `*.egg-info/`.

- [ ] **Step 2: Escrever os testes que falham**

```python
FULL = """
game_name: "Grand Theft Auto VI"
streamers:
  - twitch: "  Shroud "
    facecam: {x: 0, y: 720, w: 480, h: 360}
  - twitch: other
selection: {max_per_day: 3}
metadata: {hashtags: ["#A", "#B"]}
"""

def test_load_full(tmp_path):
    cfg = load_config(write(tmp_path, FULL))
    assert cfg.game_name == "Grand Theft Auto VI"
    assert cfg.streamers == (Streamer("shroud", Rect(0, 720, 480, 360)), Streamer("other"))
    assert cfg.selection == SelectionConfig(max_per_day=3)
    assert cfg.hashtags == ("#A", "#B")

def test_defaults(tmp_path):
    cfg = load_config(write(tmp_path, 'game_name: "X"'))
    assert cfg.streamers == ()
    assert cfg.selection == SelectionConfig(6, 30, 15, 60, 2, 5)
    assert cfg.hashtags == ("#GTA6", "#GTAVI", "#shorts")

@pytest.mark.parametrize("text, fragment", [
    ("streamers: []", "game_name"),
    ('game_name: "X"\nselection: {min_duration: 70}', "min_duration"),
    ('game_name: "X"\nstreamers: [{twitch: a, facecam: {x: 0, y: 0, w: 0, h: 10}}]', "facecam"),
    ('game_name: "X"\nstreamrs: []', "streamrs"),
    ("- not a mapping", "config"),
])
def test_invalid(tmp_path, text, fragment):
    with pytest.raises(ConfigError, match=fragment):
        load_config(write(tmp_path, text))

def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")
```

- [ ] **Step 3: Correr e confirmar que falham**

Run: `pytest tests/test_config.py -v` — Expected: FAIL (`ModuleNotFoundError: clipper`)

- [ ] **Step 4: Implementar `clipper/models.py` e `clipper/config.py`**

Chaves desconhecidas em qualquer nível são erro. Os logins são normalizados com `strip().lower()`.

- [ ] **Step 5: Criar `config.yaml`** com `game_name: "Grand Theft Auto VI"`, `streamers: []` e os restantes valores por omissão escritos por extenso, com um comentário de exemplo para `facecam`.

- [ ] **Step 6: Correr os testes** — `pytest tests/test_config.py -v` — Expected: PASS

- [ ] **Step 7: Commit** — `git commit -m "feat: project scaffold, models and config loader"`

---

### Task 2: Sondagem do risco 1 — download da Twitch no GitHub Actions

Depende de o repositório existir no GitHub. Se ainda não existir, avançar para a Task 3 e voltar aqui assim que existir.

**Files:**
- Create: `.github/workflows/probe.yml`

- [ ] **Step 1: Criar o workflow** só com `workflow_dispatch`, com um parâmetro `channel` (por omissão `shroud`). Passos: instalar `yt-dlp` e `ffmpeg`; listar os clips da semana com `yt-dlp --flat-playlist --playlist-end 3 "https://www.twitch.tv/<channel>/clips?range=7d"`; descarregar o primeiro; imprimir `ffprobe` do ficheiro.

- [ ] **Step 2: Fazer push e correr** — `gh workflow run probe.yml`, depois `gh run watch`.
Expected: o passo de `ffprobe` mostra um vídeo H.264 com áudio.

- [ ] **Step 3: Registar o resultado.** Se passar, continuar. Se falhar com bloqueio de rede ou de IP, parar e avisar o utilizador: a spec prevê mover download e edição para o PC, o que altera as Tasks 12 e 13.

- [ ] **Step 4: Commit** — `git commit -m "ci: add Twitch download probe workflow"`

---

### Task 3: Estado

**Files:**
- Create: `clipper/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `Clip`, `Moment` (Task 1)
- Produces:
  - `class StateError(Exception)`
  - `State.load(path: Path) -> State` (classmethod), `State.save(path: Path) -> None`
  - `State.done_ids() -> set[str]`, `State.delivered_moments() -> list[Moment]`, `State.delivered_today(now: datetime) -> int`
  - `State.record_delivered(clip: Clip, now: datetime) -> None`, `State.record_failure(clip: Clip, now: datetime) -> None`
  - `State.prune(now: datetime, days: int = 14) -> None`

Formato em disco: `{"version": 1, "clips": {"<id>": {"broadcaster_id", "video_id", "vod_offset", "created_at", "status", "attempts", "updated_at"}}}`, com `status` em `delivered | retry | failed`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_missing_file_is_empty(tmp_path):
    assert State.load(tmp_path / "s.json").done_ids() == set()

@pytest.mark.parametrize("content", ["", "{not json", '{"version": 2, "clips": {}}', "[]"])
def test_corrupt_file_raises(tmp_path, content):
    p = tmp_path / "s.json"; p.write_text(content)
    with pytest.raises(StateError):
        State.load(p)

def test_roundtrip(tmp_path):
    s = State.load(tmp_path / "s.json"); s.record_delivered(clip("a"), NOW)
    s.save(tmp_path / "sub" / "s.json")
    again = State.load(tmp_path / "sub" / "s.json")
    assert again.done_ids() == {"a"}
    assert again.delivered_moments() == [clip("a").moment]

def test_failure_becomes_final_on_third_attempt():
    s = State(); c = clip("a")
    s.record_failure(c, NOW); s.record_failure(c, NOW)
    assert "a" not in s.done_ids()
    s.record_failure(c, NOW)
    assert "a" in s.done_ids()
    assert s.delivered_moments() == []

def test_delivered_after_retry_counts_as_delivered():
    s = State(); s.record_failure(clip("a"), NOW); s.record_delivered(clip("a"), NOW)
    assert s.delivered_today(NOW) == 1

def test_delivered_today_uses_utc_date():
    s = State()
    s.record_delivered(clip("a"), datetime(2026, 11, 19, 23, 59, tzinfo=UTC))
    s.record_delivered(clip("b"), datetime(2026, 11, 20, 0, 1, tzinfo=UTC))
    assert s.delivered_today(datetime(2026, 11, 20, 12, 0, tzinfo=UTC)) == 1

def test_prune_drops_entries_older_than_14_days():
    s = State(); s.record_delivered(clip("old"), NOW - timedelta(days=15)); s.record_delivered(clip("new"), NOW)
    s.prune(NOW)
    assert s.done_ids() == {"new"}
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_state.py -v`
- [ ] **Step 3: Implementar `clipper/state.py`.** `save` escreve JSON com `indent=2` e `sort_keys=True` (diferenças legíveis nos commits) e cria a pasta se faltar.
- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: persistent state of processed clips"`

---

### Task 4: Seleção

**Files:**
- Create: `clipper/selection.py`
- Test: `tests/test_selection.py`

**Interfaces:**
- Consumes: `Clip`, `Moment`, `SelectionConfig`
- Produces:
  - `same_moment(a: Moment, b: Moment) -> bool`
  - `score(clip: Clip, now: datetime) -> float`
  - `select(clips: list[Clip], *, game_id: str, cfg: SelectionConfig, done_ids: set[str], seen_moments: list[Moment], delivered_today: int, now: datetime) -> list[Clip]`

- [ ] **Step 1: Escrever os testes que falham**

Os testes usam os auxiliares de `tests/helpers.py` (Task 1). `args(**over)` devolve os argumentos nomeados de `select` com `game_id="123"`, `cfg=SelectionConfig()`, conjuntos vazios, `delivered_today=0` e `now=NOW`; `ids(clips)` devolve a lista de identificadores.

```python
def test_same_moment_same_vod_within_60s():
    assert same_moment(m(video="v1", offset=100), m(video="v1", offset=159))
    assert not same_moment(m(video="v1", offset=100), m(video="v1", offset=160))
    assert not same_moment(m(video="v1", offset=100), m(video="v2", offset=100))

def test_same_moment_without_vod_uses_created_at_within_120s():
    a = m(video=None, offset=None, created=NOW)
    assert same_moment(a, m(video=None, offset=None, created=NOW + timedelta(seconds=119)))
    assert not same_moment(a, m(video=None, offset=None, created=NOW + timedelta(seconds=120)))
    assert same_moment(a, m(video="v1", offset=5, created=NOW + timedelta(seconds=10)))
    assert not same_moment(a, m(video=None, offset=None, created=NOW, broadcaster="other"))

def test_score_is_views_per_minute_with_10_minute_floor():
    assert score(clip(views=600, created=NOW - timedelta(minutes=60)), NOW) == 10.0
    assert score(clip(views=600, created=NOW - timedelta(minutes=1)), NOW) == 60.0

def test_select_filters():
    clips = [clip("ok"), clip("wrong_game", game="999"), clip("short", duration=14.9),
             clip("long", duration=60.1), clip("few", views=29), clip("done")]
    assert ids(select(clips, **args(done_ids={"done"}))) == ["ok"]

def test_select_bounds_are_inclusive():
    clips = [clip("a", duration=15, views=30, created=T0), clip("b", duration=60, created=T0 + HOUR)]
    assert len(select(clips, **args(cfg=SelectionConfig(max_per_run=5)))) == 2

def test_select_orders_by_score_and_caps_per_run():
    clips = [clip("slow", views=100, created=T0), clip("fast", views=900, created=T0 + HOUR),
             clip("mid", views=300, created=T0 + 2 * HOUR)]
    assert ids(select(clips, **args())) == ["fast", "mid"]

def test_select_respects_daily_cap():
    clips = [clip("fast", views=900, created=T0 + HOUR), clip("slow", views=100, created=T0)]
    assert ids(select(clips, **args(delivered_today=4))) == ["fast"]
    assert select(clips, **args(delivered_today=5)) == []

def test_select_skips_duplicates_of_seen_and_of_chosen():
    best = clip("best", views=900, video="v1", offset=100)
    dupe = clip("dupe", views=800, video="v1", offset=120)
    seen = clip("seen", views=700, video="v2", offset=10)
    other = clip("other", views=50, video="v3", offset=0)
    out = select([best, dupe, seen, other], **args(seen_moments=[m(video="v2", offset=30)]))
    assert ids(out) == ["best", "other"]
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_selection.py -v`
- [ ] **Step 3: Implementar `clipper/selection.py`.**

Regra de `same_moment`: se ambos têm `video_id` e `vod_offset`, é o mesmo momento quando `video_id` coincide e a diferença de `vod_offset` é inferior a 60; caso contrário, quando `broadcaster_id` coincide e a diferença de `created_at` é inferior a 120 segundos.

- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: clip selection, dedupe and ranking"`

---

### Task 5: Cliente da Twitch

**Files:**
- Create: `clipper/twitch.py`
- Test: `tests/test_twitch.py`

**Interfaces:**
- Consumes: `Clip`
- Produces:
  - `class TwitchError(Exception)`, `class TwitchAuthError(TwitchError)`
  - `User(id: str, login: str, display_name: str)` (dataclass congelada)
  - `TwitchClient(client_id: str, client_secret: str, session: requests.Session | None = None)`
  - `.get_game_id(name: str) -> str | None`
  - `.get_users(logins: list[str]) -> dict[str, User]` (chave: login em minúsculas)
  - `.get_clips(user: User, started_at: datetime, ended_at: datetime) -> list[Clip]`

Endpoints: `POST https://id.twitch.tv/oauth2/token` (`grant_type=client_credentials`); `GET https://api.twitch.tv/helix/games?name=`; `GET /helix/users?login=` (repetido); `GET /helix/clips?broadcaster_id=&started_at=&ended_at=&first=100`. Cabeçalhos `Client-Id` e `Authorization: Bearer`. Tempo limite de 15 segundos por pedido.

- [ ] **Step 1: Escrever os testes que falham** (com a biblioteca `responses`)

```python
def test_token_is_requested_once_and_sent_as_bearer(): ...
    # dois pedidos à API → 1 chamada ao endpoint de token; header "Authorization: Bearer tok"; "Client-Id: cid"

def test_bad_credentials_raise_auth_error():        # token devolve 400 → TwitchAuthError
def test_api_error_raises_twitch_error():           # /helix/clips devolve 500 → TwitchError (não TwitchAuthError)

def test_get_game_id():
    # data=[{"id": "123"}] → "123"; data=[] → None

def test_get_users_maps_by_lowercase_login_and_omits_unknown():
    # pedido ["Shroud", "ghost"]; resposta só com Shroud → {"shroud": User("1", "shroud", "Shroud")}

def test_get_clips_parses_fields():
    c = client.get_clips(USER, START, END)[0]
    assert c == Clip(id="Abc", url="https://clips.twitch.tv/Abc", broadcaster_id="1",
                     broadcaster_login="shroud", broadcaster_name="Shroud", title="wow",
                     game_id="123", view_count=42,
                     created_at=datetime(2026, 11, 19, 10, 0, tzinfo=UTC),
                     duration=29.5, video_id="v9", vod_offset=1234)

def test_get_clips_without_vod():
    # "video_id": "" e "vod_offset": null → video_id is None e vod_offset is None

def test_get_clips_sends_rfc3339_range():
    # query: started_at="2026-11-19T04:00:00Z", ended_at="2026-11-19T10:00:00Z", first="100"

def test_get_clips_follows_cursor_up_to_three_pages():
    # 4 páginas disponíveis, cada uma com cursor → exatamente 3 pedidos, clips das 3 concatenados
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_twitch.py -v`
- [ ] **Step 3: Implementar `clipper/twitch.py`.**
- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: Twitch Helix client"`

---

### Task 6: Título e descrição

**Files:**
- Create: `clipper/metadata.py`
- Test: `tests/test_metadata.py`

**Interfaces:**
- Consumes: `Clip`
- Produces:
  - `build_title(clip_title: str, streamer_name: str, tag: str, max_len: int = 100) -> str`
  - `build_description(clip: Clip, hashtags: tuple[str, ...]) -> str`

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_title_format():
    assert build_title("He did WHAT", "Shroud", "#GTA6") == "He did WHAT | Shroud #GTA6"

def test_title_truncates_clip_part_and_keeps_suffix():
    t = build_title("x" * 200, "Shroud", "#GTA6")
    assert len(t) == 100 and t.endswith("… | Shroud #GTA6")

def test_title_collapses_whitespace_and_handles_empty():
    assert build_title("  a \n b  ", "S", "#T") == "a b | S #T"
    assert build_title("   ", "S", "#T") == "S #T"

def test_description():
    assert build_description(CLIP, ("#GTA6", "#shorts")) == (
        "🎥 Shroud → https://twitch.tv/shroud\n"
        "Clip: https://clips.twitch.tv/Abc\n"
        "\n"
        "#GTA6 #shorts"
    )
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_metadata.py -v`
- [ ] **Step 3: Implementar `clipper/metadata.py`.**
- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: title and description builders"`

---

### Task 7: Leitura de metadados de vídeo e download

**Files:**
- Create: `clipper/media.py`, `clipper/download.py`, `tests/conftest.py`
- Test: `tests/test_media.py`, `tests/test_download.py`

**Interfaces:**
- Produces:
  - `MediaInfo(width: int, height: int, duration: float, fps: float, has_audio: bool)` (dataclass congelada)
  - `probe(path: Path) -> MediaInfo`, `class MediaError(Exception)`
  - `download_clip(url: str, dest_dir: Path) -> Path`, `class DownloadError(Exception)`
  - Em `tests/conftest.py`: `make_video(tmp_path, *, width=1920, height=1080, seconds=3, fps=30, audio=True) -> Path` (fixture de fábrica que gera o vídeo com `ffmpeg -f lavfi -i testsrc` e `sine`)

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_probe(make_video):
    info = probe(make_video(width=1280, height=720, seconds=2, fps=60))
    assert (info.width, info.height, info.has_audio) == (1280, 720, True)
    assert info.fps == pytest.approx(60) and info.duration == pytest.approx(2, abs=0.2)

def test_probe_without_audio(make_video):
    assert probe(make_video(audio=False)).has_audio is False

def test_probe_not_a_video(tmp_path):
    p = tmp_path / "x.mp4"; p.write_text("nope")
    with pytest.raises(MediaError):
        probe(p)

def test_download_returns_file_path(monkeypatch, tmp_path):
    # YoutubeDL falso que cria dest_dir/"Abc.mp4" → download_clip devolve esse caminho

def test_download_wraps_errors(monkeypatch, tmp_path):
    # YoutubeDL falso que lança yt_dlp.utils.DownloadError → clipper.download.DownloadError
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_media.py tests/test_download.py -v`
- [ ] **Step 3: Implementar.** `probe` usa `ffprobe -of json -show_streams -show_format`. `download_clip` usa a API Python do `yt_dlp` com `format="best[ext=mp4]/best"`, `outtmpl=dest_dir/"%(id)s.%(ext)s"`, `quiet=True`, `retries=3`.
- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: media probe and clip download"`

---

### Task 8: Deteção da facecam

**Files:**
- Create: `clipper/facecam.py`, `assets/models/face_detection_yunet_2023mar.onnx`
- Test: `tests/test_facecam.py`

**Interfaces:**
- Consumes: `Rect`
- Produces:
  - `stable_face(boxes_per_frame: list[list[Rect]], frame_w: int) -> Rect | None`
  - `face_to_region(face: Rect, frame_w: int, frame_h: int) -> Rect`
  - `clamp_region(region: Rect, frame_w: int, frame_h: int) -> Rect | None`
  - `detect_facecam(video: Path, samples: int = 10) -> Rect | None`

- [ ] **Step 1: Descarregar o modelo** de `https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx` para `assets/models/` (licença MIT).

- [ ] **Step 2: Escrever os testes que falham**

```python
FACE = Rect(100, 800, 80, 80)

def test_stable_face_found_when_present_in_60_percent():
    frames = [[FACE]] * 6 + [[]] * 4
    assert stable_face(frames, 1920) == FACE

def test_stable_face_missing_below_60_percent():
    assert stable_face([[FACE]] * 5 + [[]] * 5, 1920) is None

def test_moving_faces_are_ignored():
    frames = [[Rect(i * 250, 300, 80, 80)] for i in range(7)]
    assert stable_face(frames, 1920) is None

def test_stable_face_wins_over_moving_game_faces():
    frames = [[Rect(i * 250, 300, 120, 120), FACE] for i in range(7)]
    assert stable_face(frames, 1920) == FACE

def test_stable_face_tolerance_is_10_percent_of_width():
    near = Rect(FACE.x + 150, FACE.y, 80, 80)      # centro a 150 px < 192
    far = Rect(FACE.x + 250, FACE.y, 80, 80)       # centro a 250 px > 192
    assert stable_face([[FACE]] * 5 + [[near]] + [[]] * 4, 1920) is not None
    assert stable_face([[FACE]] * 5 + [[far]] + [[]] * 4, 1920) is None

def test_no_frames():
    assert stable_face([], 1920) is None

def test_region_has_cam_aspect_contains_face_and_fits_frame():
    r = face_to_region(FACE, 1920, 1080)
    assert r.w / r.h == pytest.approx(1080 / 768, rel=0.02)
    assert r.x <= FACE.x and r.x + r.w >= FACE.x + FACE.w
    assert r.y <= FACE.y and r.y + r.h >= FACE.y + FACE.h
    assert r.x >= 0 and r.y >= 0 and r.x + r.w <= 1920 and r.y + r.h <= 1080
    assert r.w % 2 == 0 and r.h % 2 == 0

def test_region_near_corner_is_shifted_inside():
    r = face_to_region(Rect(1850, 1010, 60, 60), 1920, 1080)
    assert r.x + r.w <= 1920 and r.y + r.h <= 1080

def test_clamp_region():
    assert clamp_region(Rect(1800, 1000, 400, 300), 1920, 1080) == Rect(1800, 1000, 120, 80)
    assert clamp_region(Rect(2000, 0, 100, 100), 1920, 1080) is None

def test_detect_facecam_returns_none_without_faces(make_video):
    assert detect_facecam(make_video()) is None
```

- [ ] **Step 3: Correr e confirmar que falham** — `pytest tests/test_facecam.py -v`
- [ ] **Step 4: Implementar `clipper/facecam.py`.**

`stable_face`: para cada caixa detetada, usada como âncora, contar os fotogramas que têm alguma caixa com o centro a menos de `0.10 * frame_w` do centro da âncora. Escolher a âncora com mais fotogramas; se a contagem for inferior a 60% dos fotogramas, devolver `None`; senão devolver a caixa mediana (mediana de `x`, `y`, `w`, `h`) das caixas agrupadas.

`face_to_region`: altura `3 * face.h`, largura `altura * 1080 / 768`, centrada horizontalmente no rosto e com o centro vertical `0.25 * face.h` abaixo do centro do rosto; depois deslocada para dentro da imagem, reduzida se exceder a imagem (mantendo a proporção) e arredondada a valores pares.

`detect_facecam`: `cv2.FaceDetectorYN` com limiar de confiança 0.8, sobre `samples` fotogramas espaçados uniformemente; devolve `face_to_region(stable_face(...))` ou `None`.

- [ ] **Step 5: Correr os testes** — Expected: PASS
- [ ] **Step 6: Commit** — `git commit -m "feat: facecam detection"`

---

### Task 9: Legendas

**Files:**
- Create: `clipper/captions.py`
- Test: `tests/test_captions.py`

**Interfaces:**
- Produces:
  - `Word(start: float, end: float, text: str)`, `Cue(start: float, end: float, text: str)` (dataclasses congeladas)
  - `transcribe(video: Path) -> list[Word]`
  - `group_words(words: list[Word], max_words: int = 4, max_gap: float = 0.6, max_chars: int = 22) -> list[Cue]`
  - `escape_ass(text: str) -> str`
  - `build_ass(cues: list[Cue], *, title: str, credit: str, title_y: int, caption_y: int, credit_y: int, duration: float) -> str`

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_group_by_max_words():
    cues = group_words(words("a b c d e"))            # palavras de 0.2 s, coladas
    assert [c.text for c in cues] == ["A B C D", "E"]
    assert cues[0].start == 0.0 and cues[0].end == pytest.approx(0.8)

def test_group_breaks_on_gap():
    w = [Word(0, 0.2, "a"), Word(0.9, 1.1, "b")]      # pausa de 0.7 s > 0.6
    assert [c.text for c in group_words(w)] == ["A", "B"]

def test_group_breaks_on_char_limit():
    cues = group_words(words("supercalifragilistic expialidocious"))
    assert len(cues) == 2

def test_group_strips_and_skips_empty_words():
    assert [c.text for c in group_words([Word(0, 0.2, " hi "), Word(0.2, 0.4, "  ")])] == ["HI"]

def test_group_empty():
    assert group_words([]) == []

@pytest.mark.parametrize("raw, expected", [
    ("a{b}c", "a(b)c"), ("a\\b", "a/b"), ("line1\nline2", "line1 line2"), ("it's 5:00 🔥", "it's 5:00 🔥"),
])
def test_escape_ass(raw, expected):
    assert escape_ass(raw) == expected

def test_build_ass_structure():
    ass = build_ass([Cue(1.0, 1.8, "HELLO")], title="T{x}", credit="twitch.tv/shroud",
                    title_y=1000, caption_y=768, credit_y=1880, duration=20.0)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Fontname" in ass and "Anton" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:03.00,Title,,0,0,0,,{\\pos(540,1000)}T(x)" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:20.00,Credit,,0,0,0,,{\\pos(540,1880)}twitch.tv/shroud" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:01.80,Caption,,0,0,0,,{\\pos(540,768)}HELLO" in ass

def test_build_ass_title_never_outlasts_short_video():
    ass = build_ass([], title="T", credit="c", title_y=1, caption_y=1, credit_y=1, duration=2.0)
    assert "0:00:00.00,0:00:02.00,Title" in ass

def test_build_ass_without_title_or_cues_is_valid():
    ass = build_ass([], title="", credit="c", title_y=1, caption_y=1, credit_y=1, duration=5.0)
    assert ",Title," not in ass and ",Caption," not in ass
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_captions.py -v`
- [ ] **Step 3: Implementar `clipper/captions.py`.**

Estilos (todos com `Fontname=Anton`, texto branco, contorno preto, alinhamento 5, margens laterais de 60): `Title` tamanho 72 e contorno 6; `Caption` tamanho 84 e contorno 6; `Credit` tamanho 36 e contorno 3. `WrapStyle: 0`.
`transcribe`: `WhisperModel("small", device="cpu", compute_type="int8")`, `word_timestamps=True`, `vad_filter=True`; devolve `[]` se o vídeo não tiver áudio ou não houver fala.

- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: captions grouping and ASS generation"`

---

### Task 10: Montagem 9:16

**Files:**
- Create: `clipper/layout.py`, `assets/fonts/Anton-Regular.ttf`, `assets/fonts/OFL.txt`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `Rect`, `MediaInfo`, `probe`, `make_video`, `build_ass`
- Produces:
  - Constantes `OUT_W = 1080`, `OUT_H = 1920`, `CAM_H = 768`, `GAME_H = 1152`, `MAX_BYTES = 50 * 1024 * 1024`
  - `text_positions(has_facecam: bool) -> dict[str, int]` com as chaves `title_y`, `caption_y`, `credit_y`
  - `build_filter(info: MediaInfo, facecam: Rect | None, ass_path: Path, fonts_dir: Path) -> str`
  - `render(src: Path, dst: Path, *, facecam: Rect | None, ass_path: Path, fonts_dir: Path, max_bytes: int = MAX_BYTES) -> None`, `class RenderError(Exception)`

- [ ] **Step 1: Descarregar o tipo de letra** de `https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf` e `.../ofl/anton/OFL.txt` para `assets/fonts/`.

- [ ] **Step 2: Escrever os testes que falham**

```python
def test_text_positions():
    assert text_positions(True) == {"title_y": 1000, "caption_y": 768, "credit_y": 1880}
    assert text_positions(False) == {"title_y": 120, "caption_y": 1560, "credit_y": 1800}

def test_filter_with_facecam_stacks_cam_over_game():
    f = build_filter(INFO_1080P30, Rect(0, 720, 480, 360), Path("a.ass"), Path("fonts"))
    assert "crop=480:360:0:720" in f and "vstack" in f and "1080:768" in f and "1080:1152" in f

def test_filter_without_facecam_uses_blurred_background():
    f = build_filter(INFO_1080P30, None, Path("a.ass"), Path("fonts"))
    assert "gblur" in f and "overlay=0:240" in f and "1080:1440" in f

def test_filter_caps_fps_at_60():
    assert "fps=60" in build_filter(replace(INFO_1080P30, fps=120.0), None, Path("a.ass"), Path("f"))
    assert "fps=30" in build_filter(INFO_1080P30, None, Path("a.ass"), Path("f"))

@pytest.mark.parametrize("facecam", [None, Rect(0, 600, 480, 360)])
@pytest.mark.parametrize("size", [(1920, 1080), (1280, 720), (640, 480), (720, 1280)])
def test_render_output_is_always_1080x1920(make_video, tmp_path, size, facecam):
    src = make_video(width=size[0], height=size[1])
    cam = clamp_region(facecam, *size) if facecam else None
    dst = render_with_ass(src, tmp_path, facecam=cam, title="it's {5}:00 \\ 🔥\nnew line")
    info = probe(dst)
    assert (info.width, info.height, info.has_audio) == (1080, 1920, True)
    assert info.duration == pytest.approx(3, abs=0.3)

def test_render_source_without_audio(make_video, tmp_path):
    info = probe(render_with_ass(make_video(audio=False), tmp_path, facecam=None, title="t"))
    assert (info.width, info.height, info.has_audio) == (1080, 1920, False)

def test_render_recompresses_to_fit_limit(make_video, tmp_path):
    dst = render_with_ass(make_video(seconds=5), tmp_path, facecam=None, title="t", max_bytes=150_000)
    assert dst.stat().st_size <= 150_000

def test_render_raises_when_limit_is_impossible(make_video, tmp_path):
    with pytest.raises(RenderError):
        render_with_ass(make_video(), tmp_path, facecam=None, title="t", max_bytes=1_000)

def test_render_failure_raises_render_error(tmp_path):
    bad = tmp_path / "bad.mp4"; bad.write_text("nope")
    with pytest.raises(RenderError):
        render(bad, tmp_path / "o.mp4", facecam=None, ass_path=tmp_path / "x.ass", fonts_dir=FONTS)
```

`render_with_ass` é um auxiliar de teste que gera o ASS com `build_ass` e `text_positions` e chama `render`.

- [ ] **Step 3: Correr e confirmar que falham** — `pytest tests/test_layout.py -v`
- [ ] **Step 4: Implementar `clipper/layout.py`.**

Grafo com facecam:

```
[0:v]split=2[c][g];
[c]crop=W:H:X:Y,scale=1080:768:force_original_aspect_ratio=increase,crop=1080:768[cam];
[g]crop='min(iw,ih*1080/1152)':'min(ih,iw*1152/1080)',scale=1080:1152[game];
[cam][game]vstack,setsar=1,fps=FPS,subtitles=ASS:fontsdir=FONTS[v]
```

Grafo sem facecam:

```
[0:v]split=2[b][f];
[b]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30[bg];
[f]crop='min(iw,ih*3/4)':'min(ih,iw*4/3)',scale=1080:1440[fg];
[bg][fg]overlay=0:240,setsar=1,fps=FPS,subtitles=ASS:fontsdir=FONTS[v]
```

Codificação: `-map [v] -map 0:a? -c:v libx264 -preset veryfast -crf N -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart`. `render` tenta `crf` 20, 26 e 32 e para no primeiro resultado dentro de `max_bytes`; se nenhum couber, lança `RenderError`. Os caminhos do ASS e dos tipos de letra são escapados para a sintaxe de filtros do `ffmpeg`.

- [ ] **Step 5: Correr os testes** — Expected: PASS
- [ ] **Step 6: Ver um resultado.** Renderizar um vídeo sintético em cada modo, extrair um fotograma ao segundo 1 e abri-lo para confirmar que título, legenda e crédito estão legíveis e nas zonas certas.
- [ ] **Step 7: Commit** — `git commit -m "feat: 9:16 layout rendering"`

---

### Task 11: Publicadores

**Files:**
- Create: `clipper/publishers/__init__.py`, `clipper/publishers/base.py`, `clipper/publishers/local.py`, `clipper/publishers/telegram.py`
- Test: `tests/test_publishers.py`

**Interfaces:**
- Consumes: `RenderedClip`
- Produces:
  - `class Publisher(Protocol)` com `publish(self, item: RenderedClip) -> None`; `class PublishError(Exception)`
  - `LocalPublisher(out_dir: Path)`: copia o vídeo para `out_dir/<clip.id>.mp4` e escreve `out_dir/<clip.id>.txt` com título, linha em branco e descrição
  - `TelegramPublisher(token: str, chat_id: str, session: requests.Session | None = None)`

- [ ] **Step 1: Escrever os testes que falham** (com `responses`)

```python
def test_local_publisher_writes_video_and_text(tmp_path): ...
    # out/Abc.mp4 com os mesmos bytes; out/Abc.txt == "TITLE\n\nDESC"

def test_telegram_sends_video_then_details():
    # 1.ª chamada: POST https://api.telegram.org/bot<token>/sendVideo, multipart com
    #   chat_id, caption == item.title, supports_streaming == "true", width == "1080", height == "1920"
    # 2.ª chamada: POST .../sendMessage com parse_mode == "HTML" e text contendo
    #   "<pre>" + html.escape(item.description) + "</pre>", o nome do streamer,
    #   "42 visualizações" e clip.url

def test_telegram_escapes_html_in_description():
    # descrição "a <b> & c" → o texto enviado contém "a &lt;b&gt; &amp; c"

def test_video_failure_raises_publish_error_and_skips_details():
    # sendVideo devolve 400 {"ok": false} → PublishError; sendMessage nunca é chamado

def test_details_failure_after_video_does_not_raise(caplog):
    # sendVideo 200, sendMessage 500 → publish() termina sem exceção; aviso no registo

def test_network_error_raises_publish_error():
    # requests.ConnectionError em sendVideo → PublishError

def test_token_never_appears_in_error_message():
    # str(PublishError) não contém o token
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_publishers.py -v`
- [ ] **Step 3: Implementar.** Tempo limite de 120 segundos em `sendVideo` e de 15 em `sendMessage`.
- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: Telegram and local publishers"`

---

### Task 12: Orquestração

**Files:**
- Create: `clipper/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: tudo o que as Tasks 1 e 3 a 11 produzem
- Produces:
  - `class GameNotFound(Exception)`
  - `RunSummary(candidates: int, delivered: int, failed: int)` (dataclass congelada)
  - `process_clip(clip: Clip, streamer: Streamer, config: Config, work_dir: Path, assets_dir: Path) -> RenderedClip`
  - `run(config: Config, state: State, twitch: TwitchClient, publisher: Publisher, *, now: datetime, process: Callable[[Clip, Streamer], RenderedClip]) -> RunSummary`

- [ ] **Step 1: Escrever os testes que falham** (Twitch, `process` e publicador falsos em memória)

```python
def test_delivers_best_clips_and_records_them():
    # 3 clips válidos, max_per_run=2 → 2 publicados por ordem de score;
    # summary == RunSummary(candidates=3, delivered=2, failed=0); state.done_ids() == os 2 ids

def test_requests_clips_for_lookback_window():
    # get_clips chamado com started_at == now - 6h e ended_at == now

def test_one_failing_clip_does_not_stop_the_next():
    # process lança no 1.º clip → o 2.º é publicado; failed == 1; o 1.º não está em done_ids

def test_publish_failure_is_recorded_and_not_counted_today():
    # publisher lança PublishError → state.delivered_today(now) == 0; failed == 1

def test_clip_is_dropped_after_three_failures():
    # 3 execuções com process a falhar → na 4.ª o clip já não é candidato

def test_unknown_streamer_is_skipped_with_warning(caplog):
    # get_users não devolve "ghost" → sem exceção; aviso contém "ghost"; os outros são tratados

def test_twitch_error_for_one_streamer_does_not_stop_the_others():
    # get_clips lança TwitchError para o streamer A → clips do B são entregues

def test_auth_error_aborts():
    # get_users lança TwitchAuthError → run propaga TwitchAuthError

def test_game_not_found_aborts():
    # get_game_id devolve None → GameNotFound com o nome do jogo na mensagem

def test_no_streamers_or_no_candidates_is_a_clean_noop():
    # summary == RunSummary(0, 0, 0); publisher nunca chamado

def test_state_is_pruned():
    # entrada com 15 dias desaparece depois de run()
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_pipeline.py -v`
- [ ] **Step 3: Implementar `clipper/pipeline.py`.**

`process_clip`: descarregar → `probe` → zona da facecam (`clamp_region` da zona manual, se existir; senão `detect_facecam`) → `transcribe` → `group_words` → `build_ass` com `text_positions`, título do clip e crédito `twitch.tv/<login>` → `render` → `RenderedClip` com `build_title` (etiqueta = primeira hashtag) e `build_description`.

`run` apanha qualquer exceção de `process` ou `publish` por clip, regista-a e chama `state.record_failure`; `TwitchAuthError` e `GameNotFound` não são apanhadas.

- [ ] **Step 4: Correr os testes** — Expected: PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: pipeline orchestration"`

---

### Task 13: Linha de comandos, workflow agendado e guia

**Files:**
- Create: `clipper/__main__.py`, `.github/workflows/clipper.yml`, `README.md`, `state/.gitkeep`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config`, `State`, `TwitchClient`, `TelegramPublisher`, `LocalPublisher`, `run`, `process_clip`
- Produces: `main(argv: list[str] | None = None) -> int`

Comando: `python -m clipper run [--config config.yaml] [--state state/state.json] [--game-name NOME] [--dry-run] [--out out] [--work work]`. `--game-name` substitui o `game_name` da configuração nessa execução.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_game_name_option_overrides_config(monkeypatch, tmp_path):
    # --game-name "Grand Theft Auto V" → o Config recebido por run tem esse game_name

def test_missing_config_returns_1(tmp_path, capsys):
    assert main(["run", "--config", str(tmp_path / "nope.yaml")]) == 1

def test_missing_env_var_is_named(monkeypatch, tmp_path, capsys):
    # sem TWITCH_CLIENT_SECRET → código 1 e stderr contém "TWITCH_CLIENT_SECRET"

def test_dry_run_does_not_need_telegram_vars_nor_touch_state(monkeypatch, tmp_path):
    # só variáveis da Twitch definidas; run substituído por um falso →
    # código 0; publicador recebido é LocalPublisher; o ficheiro de estado não é criado

def test_normal_run_saves_state(monkeypatch, tmp_path):
    # run falso → código 0; o ficheiro de estado existe; publicador é TelegramPublisher

def test_corrupt_state_returns_1(monkeypatch, tmp_path):
    # ficheiro de estado com "{" → código 1; run nunca é chamado

def test_auth_error_returns_1(monkeypatch, tmp_path):
    # run falso lança TwitchAuthError → código 1

def test_secret_values_never_printed(monkeypatch, tmp_path, capsys):
    # depois de qualquer execução, stdout+stderr não contêm os valores dos segredos
```

- [ ] **Step 2: Correr e confirmar que falham** — `pytest tests/test_cli.py -v`
- [ ] **Step 3: Implementar `clipper/__main__.py`.** No fim imprime uma linha de resumo: `candidatos=N entregues=N falhados=N`.
- [ ] **Step 4: Correr toda a suite** — `pytest -v` — Expected: PASS

- [ ] **Step 5: Criar `.github/workflows/clipper.yml`**

- `on`: `schedule: "*/15 * * * *"` e `workflow_dispatch` com os parâmetros `dry_run` (booleano) e `game_name` (texto opcional, substitui o do `config.yaml` nessa execução).
- `concurrency: {group: clipper, cancel-in-progress: false}`; `permissions: contents: write`; `timeout-minutes: 14`.
- Passos: checkout; Python 3.12 com cache do pip; `apt-get install -y ffmpeg`; cache de `~/.cache/huggingface`; `pip install .`; `python -m clipper run` com os quatro segredos em `env`; em `dry_run`, publicar a pasta `out/` como artefacto; caso contrário, fazer commit de `state/state.json` se tiver mudado (`git pull --rebase` antes do `git push`).

- [ ] **Step 6: Escrever `README.md`** em português: o que o sistema faz; guia passo a passo dos quatro passos manuais da spec (aplicação na Twitch, bot do Telegram e identificador do chat, segredos no GitHub, lista de streamers); como ensaiar com `dry_run` e outro jogo; como ajustar a zona da facecam; como parar o sistema (desativar o workflow).

- [ ] **Step 7: Ensaio de ponta a ponta** (precisa do repositório no GitHub e dos segredos da Twitch)

Run: `gh workflow run clipper.yml -f dry_run=true -f game_name="Grand Theft Auto V"`, depois `gh run watch`.
Expected: execução verde; o artefacto contém pelo menos um `.mp4` de 1080×1920 com legendas e um `.txt`. Ver o vídeo antes de continuar.

- [ ] **Step 8: Ensaio real** (precisa também dos segredos do Telegram)

Run: `gh workflow run clipper.yml -f game_name="Grand Theft Auto V"`
Expected: o utilizador recebe o vídeo e a mensagem de descrição no Telegram; aparece um commit de `state/state.json`.

- [ ] **Step 9: Commit** — `git commit -m "feat: CLI, scheduled workflow and setup guide"`
