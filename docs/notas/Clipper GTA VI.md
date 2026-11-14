---
tipo: projeto
projeto: Clipper GTA VI
estado: a funcionar com gancho e capa
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
- [x] Bot do Telegram criado (@gtaVIclipperobot, «Clipper GTA») e chaves guardadas no GitHub
- [x] Entrega de teste no Telegram (14/11: 2 clips do hasanabi recebidos)
- [x] Ramo `ensaio` apagado no GitHub
- [x] Gancho (momento mais forte primeiro + frase da IA), legendas palavra a palavra e capa
- [x] Kit do canal (Wasted Clips): nome, bio, avatar, banner
- [x] Canal de factos com o MoneyPrinterTurbo (2 vídeos por dia)
- [x] Chave do Pixabay guardada (`PIXABAY_API_KEY`)
- [ ] Abrir os canais no YouTube e no TikTok (ver `docs/canal/` no repositório)
- [ ] A 19/11: confirmar que chegam clips de GTA VI

## Como funciona

1. Vê os clips que os espectadores criaram nas últimas 6 horas nos canais
   da lista (páginas públicas da Twitch; não precisa de chaves da Twitch).
2. Filtra por duração (15 a 60 s) e visualizações (30 ou mais), ordena pela
   velocidade a que ganham visualizações e confirma que são de GTA VI.
3. Ignora clips repetidos do mesmo momento.
4. Edita: 1080×1920, facecam em cima e jogo em baixo (deteção automática).
   **Gancho:** o vídeo abre com o momento mais alto do clip (1,5 s) e uma
   frase curta em amarelo escrita pela IA (GitHub Models, grátis); depois recomeça o clip. Legendas
   de 3 palavras com a palavra dita a amarelo. Crédito ao streamer.
5. Envia para o Telegram: a capa, o vídeo com o título (escrito pela IA), e
   a descrição pronta a copiar (abre com o gancho e tem o #streamer).

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

### IA dos ganchos

Não precisa de chave: usa o GitHub Models, grátis. O Gemini gratuito não
existe na Europa (só pago), por isso a chave `GEMINI_API_KEY` que guardaste
não é usada; podes apagá-la ou deixá-la.

### Chave do Pixabay (2 minutos, grátis)

1. Criar conta em <https://pixabay.com/> e abrir <https://pixabay.com/api/docs/>.
2. A chave aparece na secção "Parameters", ao lado de `key`.
3. Guardar no mesmo sítio como `PIXABAY_API_KEY`.

(O Pexels suspendeu as chaves novas em novembro de 2026.)

### Canais

Tudo em `docs/canal/` no repositório: nome **Wasted Clips**, bio, avatar,
banner e como publicar cada vídeo. O canal de factos (sugestão: **Real Vice
City**) tem de ser **separado**: o YouTube não paga a canais de vídeos em
massa feitos com IA, e avalia o canal inteiro.

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
