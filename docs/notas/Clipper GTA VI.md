---
tipo: projeto
projeto: Clipper GTA VI
estado: a funcionar, falta o bot do Telegram
atualizado: 2026-11-14
repositorio: https://github.com/bieis-stack/gta6-clipper
tags: [projeto, gta6, clips, automacao]
---

# Clipper GTA VI

Sistema gratuito que apanha clips de GTA VI dos streamers mais vistos da
Twitch, edita-os em vertical e mos envia para o Telegram, prontos a publicar
no YouTube Shorts e no TikTok. Os streamers deram autorização para clipar.

- Repositório: <https://github.com/bieis-stack/gta6-clipper>
- Lançamento do GTA VI: **19 de novembro de 2026** (consolas)
- Corre sozinho no GitHub Actions, de 15 em 15 minutos

## Estado

- [x] Sistema construído e testado (210 testes automáticos)
- [x] Código no GitHub, agendamento ligado e a correr
- [x] Lista de 10 streamers preenchida
- [x] Ensaio completo com clips reais (Minecraft do CaseOh): vídeos bons
- [ ] **Criar o bot do Telegram e guardar as duas chaves no GitHub**
- [ ] Entrega de teste no Telegram
- [ ] Apagar o ramo `ensaio` no GitHub (tem fotogramas de uma stream)
- [ ] A 19/11: confirmar que chegam clips de GTA VI

## Como funciona

1. Vê os clips que os espectadores criaram nas últimas 6 horas nos canais
   da lista (páginas públicas da Twitch; não precisa de chaves da Twitch).
2. Filtra por duração (15 a 60 s) e visualizações (30 ou mais), ordena pela
   velocidade a que ganham visualizações e confirma que são de GTA VI.
3. Ignora clips repetidos do mesmo momento.
4. Edita: 1080×1920, facecam em cima e jogo em baixo (deteção automática),
   legendas queimadas, título nos primeiros 3 s, crédito ao streamer.
5. Envia para o Telegram: o vídeo com o título, e a descrição pronta a copiar.

Limites: 2 clips por execução, 5 por dia (dia em UTC). Muda-se em
`config.yaml`.

## Decisões tomadas

- **Publicação manual a partir do Telegram.** YouTube e TikTok bloqueiam em
  privado os vídeos enviados por aplicações não auditadas, e a auditoria
  exige a integração a funcionar. Automatizar a publicação é a Fase 3.
- **Nada público.** Os clips só vão para o Telegram. Sem o bot, o sistema só
  vigia: não edita nem gasta clips, e se houver clips bons o GitHub manda
  um email a avisar.
- **Repositório público**, porque só assim o GitHub Actions é gratuito sem
  limite de minutos. As chaves ficam escondidas nos Secrets.
- **Streamers:** caedrel, kaicenat, hasanabi, theburntpeanut, jynxzi,
  zackrawrr, xqc, caseoh_, ibai, rubius (os mais vistos de 2026). Quem não
  jogar GTA não gera clips.

## Monetização (o que a pesquisa encontrou)

- O YouTube avalia o canal inteiro pela política de conteúdo reutilizado; a
  autorização dos streamers não chega. A edição ajuda; mudar o título ou
  acrescentar algo teu antes de publicar ajuda mais.
- TikTok Creator Rewards: vídeos de 60 s ou mais, 10 mil seguidores, 100 mil
  visualizações em 30 dias. Portugal não aparece nas listas de países.
- Campanhas de clipping pagas (cerca de 1 dólar por mil visualizações):
  perguntar aos streamers se têm uma.

## Falta fazer

### Bot do Telegram (3 minutos, no telemóvel)

1. Procurar **@BotFather**, carregar em **Iniciar**, enviar `/newbot`.
2. Dar um nome e um nome de utilizador que acabe em `bot`.
3. Copiar o **token** que ele devolve.
4. Abrir a ligação `t.me/...` do bot novo e carregar em **Iniciar**.
5. Procurar **@userinfobot**, carregar em **Iniciar** e copiar o **Id**.
6. Guardar em
   <https://github.com/bieis-stack/gta6-clipper/settings/secrets/actions>
   (separador **Secrets**, **Repository secrets**):
   - `TELEGRAM_BOT_TOKEN` = o token
   - `TELEGRAM_CHAT_ID` = o Id

### Apagar o ramo `ensaio`

<https://github.com/bieis-stack/gta6-clipper/branches> → caixote do lixo ao
lado de `ensaio`.

## Fases seguintes

- **Fase 2:** clips das lives do YouTube, a correr no portátil (o YouTube
  bloqueia downloads vindos de servidores na nuvem).
- **Fase 3:** publicação automática no YouTube e no TikTok pelas APIs
  oficiais, e pedido das auditorias.

## Para retomar com o Claude

Colar o conteúdo de `docs/HANDOFF.md` do repositório no início de uma
conversa nova. Tem o contexto técnico completo.

## Ficheiros úteis no repositório

- `README.md`: guia de instalação e de uso
- `config.yaml`: streamers, jogo e limites
- `docs/HANDOFF.md`: contexto para outro Claude
- `docs/superpowers/specs/`: desenho da Fase 1
- `docs/superpowers/plans/`: plano de implementação da Fase 1
