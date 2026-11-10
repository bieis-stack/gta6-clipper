# Clipper GTA VI — Fase 1: Twitch → edição → Telegram

Data: 2026-11-10 · Estado: para revisão

## Objetivo

Maximizar visualizações (e, por arrasto, receita) de clips de GTA VI de
streamers que autorizaram o uso do seu conteúdo. A Fase 1 entrega, sem custos,
clips verticais prontos a publicar no telemóvel do dono do canal, que os
publica à mão no YouTube e no TikTok.

Critério de sucesso: no dia do lançamento (19 de novembro de 2026), o sistema
corre sozinho e entrega no Telegram, sem intervenção, até 5 clips editados por
dia, cada um poucos minutos depois de começar a ganhar tração na Twitch.

## Fora de âmbito (fases seguintes)

- Fase 2: coletor de lives do YouTube, a correr no PC do utilizador.
- Fase 3: publicação automática pelas APIs oficiais do YouTube e do TikTok.
- Estatísticas de desempenho, interface gráfica, vários canais de destino.

## Decisões já tomadas

| Tema | Decisão |
|---|---|
| Publicação | Manual, a partir do Telegram, até as auditorias das APIs passarem |
| Onde corre | GitHub Actions, agendado de 15 em 15 minutos |
| Origem dos clips | Clips criados por espectadores, obtidos pela API oficial da Twitch |
| Formato | 1080×1920, facecam em cima e gameplay em baixo; corte com zoom quando não há facecam |
| Legendas | Geradas por Whisper e queimadas no vídeo |
| Custos | Zero: só serviços e bibliotecas gratuitos |

## Arquitetura

Um pacote Python (`clipper`) com uma unidade por responsabilidade. Cada
unidade é testável isoladamente e só comunica com as outras por dados simples.

| Unidade | Faz | Depende de |
|---|---|---|
| `config` | Lê e valida `config.yaml` | — |
| `twitch` | Autentica-se e pede utilizadores, jogo e clips à API Helix | rede |
| `selection` | Filtra, remove repetidos e ordena candidatos (funções puras) | — |
| `state` | Regista clips já tratados e a contagem diária | ficheiro JSON |
| `download` | Descarrega o vídeo de um clip com `yt-dlp` | rede |
| `facecam` | Encontra a zona da facecam no vídeo | OpenCV |
| `captions` | Transcreve o áudio e gera legendas em formato ASS | faster-whisper |
| `layout` | Monta o vídeo 9:16 final com `ffmpeg` | ffmpeg |
| `metadata` | Gera título, descrição e hashtags | — |
| `publishers.telegram` | Envia vídeo e textos para o Telegram | rede |
| `pipeline` | Orquestra uma execução completa | todas as anteriores |

`publishers` é uma interface com um método (`publish(clip)`). O Telegram é a
única implementação da Fase 1; YouTube e TikTok entram na Fase 3 sem alterar o
resto.

## Fluxo de uma execução

1. Carregar a configuração e o estado.
2. Obter o identificador do jogo a partir do nome configurado.
3. Para cada streamer, pedir os clips criados nas últimas `lookback_hours`.
4. Selecionar (ver abaixo) no máximo `max_per_run` clips.
5. Para cada clip selecionado: descarregar, detetar facecam, transcrever,
   montar, gerar textos e enviar para o Telegram.
6. Gravar o estado e fazer commit dele no repositório.

## Seleção

Um clip é candidato quando cumpre todas as condições:

- pertence ao jogo configurado;
- dura entre `min_duration` e `max_duration` segundos;
- tem pelo menos `min_views` visualizações;
- ainda não foi tratado;
- não é o mesmo momento de outro clip já tratado ou já escolhido nesta
  execução. Dois clips são o mesmo momento quando vêm do mesmo VOD e começam a
  menos de 60 segundos um do outro; sem informação de VOD, quando são do mesmo
  streamer e foram criados a menos de 120 segundos um do outro.

Os candidatos ordenam-se por velocidade: visualizações a dividir pela idade em
minutos (com mínimo de 10 minutos, para um clip acabado de criar não ganhar
por acaso). Escolhem-se os primeiros, respeitando `max_per_run` e o que falta
de `max_per_day`.

O sistema não corta clips da Twitch: o espectador já escolheu o início e o
fim, e um corte cego arrisca-se a tirar o desfecho. Por isso a duração é um
filtro (15 a 60 segundos por omissão). O alvo de 20 a 45 segundos aplica-se
na Fase 2, onde o corte é decidido pelo sistema.

## Edição

Saída: MP4 H.264 + AAC, 1080×1920, taxa de fotogramas da origem (máximo 60),
abaixo de 50 MB (limite de envio de bots do Telegram; se passar, recodifica-se
com mais compressão).

**Com facecam:** facecam nos 40% de cima (1080×768), gameplay nos 60% de baixo
(1080×1152, corte central da imagem original).

**Sem facecam:** corte central 3:4 da imagem original, ampliado para
1080×1440, sobre uma versão desfocada da mesma imagem a preencher o fundo.

**Deteção da facecam:** amostram-se cerca de 10 fotogramas e corre-se um
detetor de rostos. Há facecam quando um rosto aparece em pelo menos 60% dos
fotogramas com o centro a menos de 10% da largura da imagem do centro
mediano (rostos de personagens do jogo mexem-se; o do streamer não). A zona recortada é o rosto alargado até ao
formato da faixa de cima. O `config.yaml` aceita uma zona manual por streamer,
que tem prioridade sobre a deteção.

**Textos sobre o vídeo:**

- título do clip em letras grandes nos primeiros 3 segundos;
- crédito `twitch.tv/<streamer>` discreto durante todo o vídeo;
- legendas de 2 a 4 palavras de cada vez, brancas com contorno preto, na
  junção entre facecam e gameplay (ou no terço inferior, sem facecam).

Tipo de letra de licença livre (OFL), incluído no repositório.

**Legendas:** modelo `small` do faster-whisper em CPU, idioma detetado
automaticamente, tempos por palavra. Sem fala detetada, o vídeo sai sem
legendas.

## Textos para publicação

- **Título:** `<título do clip> | <nome do streamer> #GTA6`, cortado aos 100
  caracteres (limite do YouTube).
- **Descrição:** linha de crédito com ligação ao canal do streamer, ligação ao
  clip original e hashtags configuráveis.

## Entrega no Telegram

Duas mensagens por clip, para um chat privado com o bot:

1. o vídeo, com o título como legenda;
2. a descrição num bloco copiável com um toque, mais o streamer, as
   visualizações na Twitch no momento e a ligação ao clip original.

## Configuração

```yaml
game_name: "Grand Theft Auto VI"
streamers:
  - twitch: nome_do_canal
    # facecam: {x: 0, y: 720, w: 480, h: 360}   # opcional
selection:
  lookback_hours: 6
  min_views: 30
  min_duration: 15
  max_duration: 60
  max_per_run: 2
  max_per_day: 5
metadata:
  hashtags: ["#GTA6", "#GTAVI", "#shorts"]
```

Para ensaiar antes do lançamento, basta trocar `game_name` por um jogo já
disponível.

Segredos, guardados nos GitHub Secrets e nunca no repositório:
`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`.

## Execução no GitHub Actions

- Agendamento de 15 em 15 minutos, mais arranque manual.
- Um grupo de concorrência impede duas execuções em simultâneo.
- O modelo do Whisper e as dependências ficam em cache.
- O estado (`state/state.json`) é gravado por commit no fim de cada execução;
  entradas com mais de 14 dias são apagadas.
- **Repositório público.** Os minutos de Actions são gratuitos e ilimitados em
  repositórios públicos; num privado, o plano gratuito dá 2000 minutos por
  mês, o que não chega para esta cadência. Consequência: o código e a lista
  de streamers ficam visíveis; os segredos não. Alternativa, se o repositório
  tiver de ser privado: executar de hora a hora.

Linha de comandos, igual no Actions e num PC:

```bash
python -m clipper run
```

```bash
python -m clipper run --dry-run
```

`--dry-run` grava os vídeos numa pasta local e não envia nada nem altera o
estado.

## Erros

- Falha num clip (download, edição ou envio) não interrompe os restantes. O
  clip fica com a tentativa registada e é abandonado à terceira falha.
- Falha global (credenciais da Twitch inválidas, configuração errada) termina
  a execução com erro; o GitHub avisa o dono do repositório por email.
- Streamer inexistente na configuração gera um aviso no registo e é ignorado.
- Sem candidatos, a execução termina com sucesso sem fazer nada.

## Testes

- **Unitários:** `selection`, `state`, `metadata`, `config`, geração das
  legendas ASS, agrupamento de rostos em `facecam` (com deteções injetadas) e
  construção do comando `ffmpeg` em `layout`.
- **Com rede simulada:** clientes `twitch` e `telegram`.
- **Integração local:** `layout` sobre um vídeo sintético gerado pelo
  `ffmpeg`, a confirmar dimensões, duração e presença de áudio na saída, nos
  dois modos (com e sem facecam).
- **Ponta a ponta:** `--dry-run` no GitHub Actions contra a Twitch real, com
  um jogo já disponível.

## Riscos

1. **Download de clips da Twitch a partir do GitHub Actions — por confirmar.**
   Não foi possível testar no ambiente onde a spec foi escrita, que bloqueia o
   acesso à Twitch. É a primeira coisa a provar na implementação. Se falhar,
   o download e a edição passam para o PC do utilizador e o Actions fica só
   com a deteção.
2. **Atrasos do agendador do GitHub.** As execuções agendadas podem atrasar
   vários minutos em horas de maior carga. Aceitável para este uso.
3. **Deteção de facecam.** Pode falhar com sobreposições invulgares; nesse
   caso o clip sai no modo sem facecam, ou corrige-se com a zona manual.
4. **Legendas em áudio de jogo.** Tiros, música e gritos degradam a
   transcrição. O dono do canal vê o clip antes de publicar e pode descartá-lo.
5. **Monetização.** A edição automática reduz, mas não elimina, o risco de o
   YouTube classificar o canal como conteúdo reutilizado.

## Passos manuais do utilizador

1. Criar uma aplicação em dev.twitch.tv (dá o `client id` e o `secret`).
2. Criar um bot no Telegram com o @BotFather e obter o identificador do chat.
3. Criar o repositório no GitHub e guardar os quatro segredos.
4. Preencher a lista de streamers em `config.yaml`.

O `README` terá um guia passo a passo para cada um.
