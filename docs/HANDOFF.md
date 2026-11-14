# Passagem de contexto — Clipper GTA VI

Cola este texto no início de uma conversa nova. Foi escrito para um modelo que
não viu nada do que aconteceu antes.

---

Vais continuar um projeto a meio. O código está no repositório público
`bieis-stack/gta6-clipper` no GitHub; começa por o ligar a esta sessão e ler o
`README.md`, a spec em `docs/superpowers/specs/` e o plano em
`docs/superpowers/plans/`. Este documento dá-te o que esses ficheiros não dizem:
quem é o utilizador, o que já foi verificado e o que falta.

## Para quem é e o que quer

O dono do projeto tem um canal de YouTube e planeia abrir um de TikTok. Quer
publicar clips de GTA VI de streamers grandes, que lhe deram autorização para
usar o conteúdo deles (não voltes a levantar a questão dos direitos de autor;
está resolvida). O jogo sai a **19 de novembro de 2026** e o sistema tem de
estar a funcionar nesse dia.

Três coisas a saber sobre como trabalhar com ele:

- **Não é programador.** Escreve em português de Portugal, em mensagens
  curtas. Explica o que fazes em linguagem simples e diz-lhe exatamente onde
  clicar quando precisares que faça algo.
- **Tudo tem de ser gratuito.** Não proponhas serviços pagos nem nada que
  consuma créditos.
- **Quer poucas perguntas.** Pediu expressamente que, antes de lhe perguntar
  algo, se procure a resposta com este critério: o que traz mais
  visualizações e, por arrasto, mais receita. Decide por ele sempre que a
  escolha seja reversível, e diz-lhe o que decidiste. Pergunta só o que só ele
  sabe (nomes de streamers, chaves, acessos).

Nunca lhe peças para colar chaves ou tokens no chat. Vão para os Secrets do
repositório no GitHub, e o `README.md` explica-lhe como.

## O que o sistema faz

De 15 em 15 minutos, no GitHub Actions:

1. pede à API oficial da Twitch os clips que os espectadores criaram nas
   últimas horas, para uma lista de streamers em `config.yaml`;
2. filtra pelo jogo, duração e visualizações, remove clips repetidos do mesmo
   momento e ordena pela velocidade a que ganham visualizações;
3. descarrega os melhores com o `yt-dlp`, deteta a facecam do streamer,
   transcreve a fala com o Whisper e monta um vídeo vertical 1080×1920 com
   título, legendas e crédito;
4. envia o vídeo e a descrição para o Telegram do dono, que publica à mão.

A publicação é manual de propósito. Tanto o YouTube como o TikTok bloqueiam
em privado os vídeos enviados pelas suas APIs por aplicações não auditadas, e
as auditorias exigem mostrar a integração a funcionar. Foi essa a razão do
desenho híbrido; não tentes automatizar a publicação por automação de browser,
que viola os termos das duas plataformas e põe em risco a conta dele.

## Em que ponto está (14 de novembro de 2026)

**O sistema está ligado e a correr sozinho** no GitHub Actions do repositório
`bieis-stack/gta6-clipper`, de 15 em 15 minutos, à espera de clips de
`Grand Theft Auto VI`. Lista de streamers já preenchida em `config.yaml`.

**Chaves:** a Twitch é opcional; o Telegram é obrigatório para entregar.

- **Fonte:** com `TWITCH_CLIENT_ID` e `TWITCH_CLIENT_SECRET`, a API oficial
  (`clipper/twitch.py`); sem elas, as páginas públicas via `yt-dlp`
  (`clipper/twitch_public.py`). A listagem pública não traz o jogo: cada
  candidato bem colocado é aberto para o saber (`resolve_game`, no máximo 12
  consultas por execução), e os de outro jogo ficam registados como
  `skipped` com o jogo, para não gastar consultas na execução seguinte.
- **Destino:** só o Telegram (`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`).
  Sem ele, o sistema só vigia: não edita nem gasta clips, e se houver clips
  prontos a execução falha com instruções (o GitHub manda email ao dono).
  **O dono escolheu explicitamente que nada seja publicado em sítios
  públicos.** Uma versão anterior entregava na página Releases do
  repositório (que é público); foi retirada a pedido dele. Não a reintroduzas
  nem publiques clips noutro sítio público sem ele o pedir.

**Verificado no GitHub real:** a listagem e o download públicos da Twitch
(clips vêm em HEVC 1920×1080); a deteção do jogo clip a clip; um ensaio
completo com clips reais de Minecraft do `caseoh_` (descarregar, facecam,
legendas, montagem), cerca de 1 minuto e meio por clip de 60 segundos; as
execuções agendadas a terminar sem erro e a gravar o estado.

**Entrega no Telegram verificada a 14/11:** bot `@gtaVIclipperobot`
("Clipper GTA"); a execução #41 com `Just Chatting` entregou 2 clips do
hasanabi e o dono confirmou que chegaram. O ramo `ensaio` foi apagado.

**Gancho, legendas e capa (14/11)**, spec em
`docs/superpowers/specs/2026-11-14-hook-design.md`: o vídeo abre com o pico de
volume do clip (1,5 s, `clipper/hook.py`); a frase do gancho e o título são
escritos pelo Gemini (`GEMINI_API_KEY`, opcional) ou pelo Pollinations, com
reserva numa lista fixa (`clipper/writer.py`); legendas de 3 palavras com a
palavra dita a amarelo; capa JPG enviada antes do vídeo. Qualquer falha
nestas partes volta ao comportamento antigo.

**Canal de factos (14/11):** `faceless/` e o workflow `faceless.yml` correm o
MoneyPrinterTurbo no Actions, 2 vídeos por dia, nicho "Real-life Vice City".
Precisa de `GEMINI_API_KEY` e `PEXELS_API_KEY`. Não foi corrido localmente (a
instalação foi bloqueada pelas permissões da sessão): a primeira verificação
é a primeira execução no GitHub.

**Kit do canal:** `docs/canal/` (nome Wasted Clips, bio, avatar, banner,
como publicar).

**Acesso a partir do portátil do dono:** o `git` global está noutra conta
(`gabrielpinacarvalho09-hue`). O clone em `C:/Users/gabri/gta6-clipper` usa o
endereço `https://bieis-stack@github.com/...` para o Git Credential Manager
pedir a conta certa. O `gh` não está instalado.

**Falta:**

1. A 19 de novembro, confirmar que chegam clips de GTA VI. O nome da
   categoria na Twitch tem de ser exatamente `Grand Theft Auto VI`; se for
   outro, corrigir `game_name` em `config.yaml`.
2. Ver a primeira execução do workflow de factos e corrigir o que falhar.

A lista de streamers foi escolhida a partir das classificações de audiência
de 2026, porque o dono disse que os dez mais populares o autorizaram. Inclui
canais que raramente jogam GTA (`caedrel`, `hasanabi`); não faz mal, mas
convém confirmar com ele se quiser afinar.

## Decisões já tomadas, e porquê

- **Clips dos espectadores em vez de deteção própria.** O público já escolheu
  o momento e o corte; a Twitch dá isso de graça pela API.
- **Facecam em cima e gameplay em baixo**, com recurso a corte ampliado sobre
  fundo desfocado quando não há facecam. É o formato mais recomendado para
  retenção; vídeo horizontal com barras rende mal.
- **Legendas queimadas no vídeo.** Foi a recomendação mais consistente entre
  as fontes consultadas; muita gente vê sem som.
- **Texto entre os 250 e os 1500 píxeis de altura.** O YouTube Shorts e o
  TikTok tapam o topo e o fundo com a sua interface.
- **Repositório público.** Só assim os minutos de Actions são ilimitados.
- **Estado guardado por commit** em `state/state.json`, gravado antes e depois
  de cada clip, para uma execução interrompida não reenviar vídeos.
- **Um clip pode perder-se, mas não duplicar-se.** Se o Telegram não responder
  depois de receber o vídeo, o clip conta como entregue.
- **Falhas fazem barulho.** Uma execução com falhas e zero entregas sai com
  erro, para o GitHub avisar o dono por email.

Os dados sobre duração e frequência ideais vêm de blogues de quem vende
ferramentas de clipping, não de testes controlados. Por isso esses valores
são configuráveis em `config.yaml`; não os trates como verdade assente.

## Notas para o dono

`docs/notas/Clipper GTA VI.md` é um resumo em linguagem simples, feito para o
cofre do Obsidian dele (pasta `OBSIDIAN CLAUDE`, no portátil). Atualiza-o quando
o estado mudar.

## Armadilhas já encontradas

- O descodificador de áudio interno do `faster-whisper` falha com o PyAV
  atual. O código contorna isso descodificando com o `ffmpeg`
  (`clipper/captions.py`, função `load_audio`). Não desfaças.
- As versões estão fixas em `constraints.txt`, exceto o `yt-dlp`, que tem de
  se atualizar quando a Twitch muda. Mantém essa exceção.
- O OpenCV 5 já não traz os detetores Haar; a deteção usa o modelo YuNet
  guardado em `assets/models/`.
- A política de conteúdo reutilizado do YouTube avalia o canal inteiro e não
  depende dos direitos de autor. A edição automática ajuda mas não garante
  monetização; o dono já foi avisado.

## O que vem depois da Fase 1

- **Fase 2:** coletor de lives do YouTube, a correr no computador do dono
  (o YouTube bloqueia downloads vindos de servidores na nuvem). Deteta picos
  de atividade no chat e corta esses momentos, com alvo de 20 a 45 segundos.
- **Fase 3:** publicação automática pelas APIs oficiais do YouTube e do
  TikTok, e pedido das auditorias. Se a publicação automática for prioritária
  para ele, esta fase pode passar à frente da Fase 2.

Cada fase teve, e deve ter, a sua spec e o seu plano antes do código.

## Pequenos pontos conhecidos e não corrigidos

A revisão independente classificou-os como menores:

- a gravação do estado não é atómica;
- o limite de 50 MB do vídeo não tem margem face ao limite do Telegram;
- um erro do servidor da Twitch no pedido de acesso é descrito como
  credenciais recusadas;
- não há nova tentativa em erros passageiros da Twitch;
- o ficheiro de estado não é validado campo a campo;
- um clip entregue sem legendas não é assinalado no Telegram;
- clips do mesmo momento podem repetir-se enquanto a Twitch não tem a
  gravação da stream;
- um título com uma única palavra muito longa sai do enquadramento;
- as ações do GitHub estão fixas por versão e não por identificador exato.

## Como trabalhar no código

Escreve o teste primeiro e vê-o falhar antes de implementar; todo o projeto
foi feito assim. Corre `pytest` no fim de cada alteração. Quando disseres ao
dono que algo funciona, diz também como o verificaste, e distingue sempre o
que testaste do que apenas esperas que funcione.
