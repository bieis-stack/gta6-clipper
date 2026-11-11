# Clipper GTA VI

Procura na Twitch os clips de GTA VI dos streamers que escolheres, edita-os em
vertical (1080×1920, com facecam em cima, legendas, título e crédito) e
envia-os para o teu Telegram, prontos a publicar no YouTube e no TikTok.

Corre sozinho no GitHub Actions, de 15 em 15 minutos, sem custos.

## Como funciona

1. Pede à Twitch os clips que os espectadores criaram nas últimas horas.
2. Fica com os do jogo certo, com duração e visualizações suficientes, e
   ordena-os pela velocidade a que estão a ganhar visualizações.
3. Ignora clips repetidos do mesmo momento.
4. Edita os melhores e envia cada um para o Telegram em duas mensagens: o
   vídeo com o título, e a descrição num bloco que se copia com um toque.

## Instalação

Precisas de um repositório no GitHub e de quatro chaves. Nenhuma chave vai
para o código: ficam guardadas nos *Secrets* do GitHub.

### 1. Repositório no GitHub

1. Em <https://github.com/new>, cria um repositório e marca-o como **Public**.
2. Envia para lá todos os ficheiros deste projeto, no ramo principal (`main`).

Tem de ser público para ser gratuito: o GitHub só oferece minutos ilimitados
de Actions a repositórios públicos. Num repositório privado o plano gratuito
dá 2000 minutos por mês, que a correr de 15 em 15 minutos se gastam em uma a
três semanas, e o sistema para. Se precisares mesmo de um repositório privado,
abre `.github/workflows/clipper.yml` e troca `*/15 * * * *` por `0 * * * *`,
para correr só de hora a hora.

### 2. Aplicação na Twitch

1. Entra em <https://dev.twitch.tv/console> com a tua conta da Twitch (tem de
   ter a autenticação de dois fatores ligada).
2. **Register Your Application**. Nome à tua escolha; em *OAuth Redirect URLs*
   escreve `http://localhost`; categoria *Application Integration*; tipo de
   cliente *Confidential*.
3. Abre a aplicação criada. Copia o **Client ID** e carrega em **New Secret**
   para obteres o **Client Secret**.

### 3. Bot do Telegram

1. No Telegram, fala com **@BotFather** e envia `/newbot`. Segue as
   perguntas. No fim recebes o **token** do bot.
2. Abre a conversa com o teu bot novo e envia-lhe uma mensagem qualquer.
3. No navegador, abre `https://api.telegram.org/bot<TOKEN>/getUpdates`,
   trocando `<TOKEN>` pelo teu token. Procura `"chat":{"id":` — o número a
   seguir é o teu **chat id**.

### 4. Chaves no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository
secret**. Cria estes quatro, com os nomes exatos:

| Nome | Valor |
|---|---|
| `TWITCH_CLIENT_ID` | Client ID da Twitch |
| `TWITCH_CLIENT_SECRET` | Client Secret da Twitch |
| `TELEGRAM_BOT_TOKEN` | token do bot |
| `TELEGRAM_CHAT_ID` | o teu chat id |

### 5. Streamers

Edita `config.yaml` e põe os canais da Twitch dos streamers que te
autorizaram. Podes escrever só o nome do canal ou colar a ligação
(`twitch.tv/nome`):

```yaml
streamers:
  - twitch: nome_do_canal
  - twitch: outro_canal
```

### 6. Ligar

Não há nada a ligar: assim que o código estiver no ramo principal, o
*Clipper* corre sozinho de 15 em 15 minutos. Vês cada execução no separador
**Actions** do repositório.

## Ensaiar antes do lançamento

Em **Actions → Clipper → Run workflow**:

- marca **dry_run** para não enviar nada para o Telegram;
- em **game_name** escreve um jogo que já exista, por exemplo
  `Grand Theft Auto V`.

Quando terminar, os vídeos ficam em **Artifacts → clips-de-ensaio**, na página
dessa execução. Vê-os antes de ligar o sistema a sério.

Para testar a entrega no Telegram, repete sem marcar **dry_run**.

Se uma execução falhar com erros de rede ao descarregar clips, corre o
workflow **Sondagem da Twitch**: confirma se os servidores do GitHub conseguem
chegar aos clips.

## Ajustes

Tudo em `config.yaml`:

- `min_views`, `min_duration`, `max_duration`: filtros dos clips.
- `max_per_run`, `max_per_day`: quantos clips recebes por execução e por dia
  (o dia conta em UTC).
- `hashtags`: vão na descrição; a primeira vai também no título.

### Facecam

A zona da facecam é detetada sozinha. Se um streamer sair mal (facecam cortada
ou clip sem facecam), indica a zona à mão, em píxeis da imagem original da
stream:

```yaml
streamers:
  - twitch: nome_do_canal
    facecam: {x: 0, y: 720, w: 480, h: 360}
```

`x` e `y` são o canto superior esquerdo; `w` e `h` a largura e a altura.

## Parar

**Actions → Clipper → ⋯ → Disable workflow**. Para retomar, **Enable
workflow**.

## Quando algo corre mal

O GitHub envia-te um email sempre que uma execução falha. Isso acontece
quando:

- uma chave está errada ou em falta (a mensagem diz qual);
- o bot do Telegram não consegue falar com o teu chat;
- houve clips para tratar e nenhum foi entregue.

Abre a execução em **Actions** para ver a causa: as linhas que começam por
`erro:` ou `WARNING` explicam o que falhou. A última linha de cada execução
resume o resultado, por exemplo `candidatos=4 entregues=2 falhados=0`.

Um clip que falhe três vezes é abandonado. Se uma execução for interrompida a
meio, o que já tinha sido entregue não volta a ser enviado.

## Bom saber

- **Agendamento.** O GitHub pode atrasar execuções agendadas alguns minutos
  em horas de muita carga, e desliga os agendamentos de repositórios sem
  atividade durante 60 dias. Enquanto o sistema entregar clips isso não
  acontece, porque cada entrega grava um commit.
- **Ensaios em fila.** Só uma execução corre de cada vez. Um ensaio manual
  que fique à espera pode ser substituído pela execução agendada seguinte;
  se isso acontecer, lança-o outra vez.
- **Estado.** O ficheiro `state/state.json` guarda os clips já tratados. O
  sistema atualiza-o sozinho com um commit; não o edites à mão.
- **Monetização.** A autorização dos streamers não garante monetização no
  YouTube: a política de conteúdo reutilizado avalia o canal como um todo.
  Ajustar o título ou acrescentar algo teu antes de publicar ajuda.
- **Repositório público.** O código e a lista de streamers ficam visíveis. As
  quatro chaves não.

## Correr no teu computador

Precisas de Python 3.11 ou mais recente e do `ffmpeg` instalado.

```bash
pip install -e ".[dev]"
```

```bash
pytest
```

```bash
python -m clipper run --dry-run
```

O último comando precisa das variáveis `TWITCH_CLIENT_ID` e
`TWITCH_CLIENT_SECRET` definidas, e grava os vídeos na pasta `out/`.

## Licenças de terceiros

- Tipo de letra Anton — SIL Open Font License 1.1 (`assets/fonts/OFL.txt`).
- Modelo de deteção de rostos YuNet, da OpenCV — licença MIT.
