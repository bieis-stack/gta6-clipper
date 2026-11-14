# Clipper GTA VI — Gancho, legendas, capa e textos

Data: 14 de novembro de 2026. Estado: aprovado pelo dono ("A e B juntos",
"faz só").

## Porquê

Os vídeos entregues no Telegram começam com o título que um espectador deu ao
clip na Twitch e seguem o clip tal como está. Quem faz scroll no TikTok ou no
YouTube Shorts decide em 1 a 2 segundos se fica. O dono quer que cada vídeo
abra com um gancho que faça um adolescente parar, e que o vídeo, a capa e os
textos de publicação estejam prontos a usar. O GTA VI sai a 19 de novembro e,
a partir de 20 de novembro, o sistema tem de funcionar sem ninguém a mexer.

## Objetivos

1. **Gancho visual ("flash-forward"):** o vídeo abre com o momento mais forte
   do clip (cerca de 1,5 s, escolhido pelo pico de volume do áudio) e depois
   recomeça o clip desde o início.
2. **Texto do gancho:** frase curta e grande em cima da imagem durante os
   primeiros segundos. Escrita por uma IA gratuita a partir do que o streamer
   diz; se a IA falhar, uma frase fixa de uma lista.
3. **Título de publicação** escrito pela mesma chamada à IA (com reserva no
   título atual).
4. **Legendas palavra a palavra:** grupos curtos, a palavra a ser dita em
   amarelo.
5. **Capa (thumbnail):** imagem 1080×1920 em JPG, com o fotograma do pico e o
   texto do gancho, enviada para o Telegram junto do vídeo.
6. **Descrição** com uma linha de gancho, crédito, ligação e hashtags.

## Fora de âmbito

- Publicação automática (Fase 3).
- Música de fundo, efeitos de zoom, voz sintética.
- O projeto MoneyPrinterTurbo (repositório à parte).

## Anti-objetivos

- Um clip deixar de ser entregue por causa do gancho. Qualquer falha no
  gancho, na IA ou na capa cai para o comportamento anterior.
- Texto enganador. O gancho tem de descrever o que acontece mesmo no clip
  (a política do YouTube sobre metadados enganadores aplica-se ao canal).
- Qualquer custo. Só serviços gratuitos.
- Publicar algo em sítios públicos. Nada de artefactos do GitHub com vídeos
  (num repositório público, qualquer conta do GitHub os descarrega).

## Restrições

- Tem de estar testado com um clip real e entregue no Telegram até 18 de
  novembro.
- Corre no GitHub Actions: 14 minutos por execução, até 2 clips, ficheiro de
  vídeo até 50 MB.
- O plano gratuito do Gemini é pequeno (cerca de 20 pedidos por dia no
  modelo Flash) e instável. Usa-se o nome `gemini-flash-latest`, mantido pela
  Google, configurável em `config.yaml`.
- Sem dependências novas: o pedido HTTP usa o `requests`, a análise do áudio
  usa o `numpy` e o `load_audio` que já existem.

## Abordagens consideradas

- **A — frase fixa + flash-forward.** Grátis e sem chaves. Os textos
  repetem-se e ficam genéricos.
- **B — frase escrita por IA.** Específica de cada clip. Depende de um
  serviço gratuito que pode mudar.
- **A + B (escolhida pelo dono).** A IA escreve a frase; se falhar, usa-se a
  frase fixa. O flash-forward funciona sempre.

Para escolher o momento forte considerámos a atividade do chat (não está
disponível nas páginas públicas), palavras-chave na transcrição (frágil) e o
volume do áudio. **Escolhido: o volume do áudio**, porque os momentos que os
espectadores clipam são quase sempre gritos e reações.

## Como funciona

### Pico (`clipper/hook.py`)

- Lê o áudio em mono a 16 kHz (`load_audio`).
- Calcula a energia em janelas de 1,5 s (passo de 0,1 s) e escolhe a janela
  com mais energia.
- Sem flash-forward se o clip tiver menos de 8 s, se não tiver áudio, ou se
  o pico começar nos primeiros 2 s (o clip já abre forte). Nesses casos fica
  só o texto do gancho.

### Montagem (`clipper/layout.py`)

- O filtro do ffmpeg corta o troço do pico (vídeo e áudio) e concatena-o
  antes do clip inteiro, e só depois aplica o enquadramento vertical e as
  legendas. O vídeo final dura mais 1,5 s.
- As legendas do clip são deslocadas 1,5 s. Durante o flash-forward não há
  legendas, só o texto do gancho.

### Texto do gancho e título (`clipper/writer.py`)

- Entrada: transcrição, título do clip na Twitch, nome do streamer, jogo.
- Pedido ao Gemini (`GEMINI_API_KEY`), com resposta em JSON:
  `{"hook": "...", "title": "..."}`. Se não houver chave ou falhar,
  tenta o Pollinations (gratuito, sem chave). Tempo máximo de 20 s cada.
- Validação: gancho com 2 a 7 palavras e até 40 caracteres, em maiúsculas,
  sem emojis (a biblioteca de legendas não desenha emojis a cores), sem
  hashtags. Título até 70 caracteres. Inválido → reserva.
- Reserva: lista de frases fixas, escolhida de forma estável a partir do id
  do clip, para não repetir sempre a mesma.
- Em inglês: os streamers falam inglês e o público do GTA é mundial.

### Legendas (`clipper/captions.py`)

- Grupos de até 3 palavras. Um evento por palavra: o grupo inteiro em
  branco, a palavra dita em amarelo e ligeiramente maior.
- Texto do gancho num estilo próprio (maior, amarelo com contorno preto), na
  posição do título atual, visível do segundo 0 até ao segundo 3.

### Capa (`clipper/cover.py`)

- Fotograma do meio do pico, enquadrado como o vídeo (o mesmo filtro), com
  o texto do gancho em grande. JPG até 1 MB.
- Enviada para o Telegram como foto, antes do vídeo, com a legenda "Capa".
  Se falhar, o vídeo segue sem capa.

### Textos para publicação

- Título: o da IA + " | streamer #GTA6"; reserva: o atual.
- Descrição: linha do gancho, crédito com ligação ao canal do streamer,
  ligação do clip, hashtags.

## Alterações depois do primeiro teste real (14/11)

- O plano gratuito do Gemini não existe na Europa (403 "free tier is not
  available for this project"). Primeiro escritor passa a ser o GitHub
  Models, com o token do workflow (`models: read`).
- O flash-forward com `split`+`trim` guardava em memória todos os fotogramas
  até ao pico; o Actions matou o processo. O troço entra agora como segunda
  entrada do ffmpeg (`-ss`/`-t`). Medido: 383 MB de pico num 60 s 1080p60
  com o pico aos 50 s.

## Configuração

```yaml
hook:
  enabled: true
  seconds: 1.5
  model: gemini-flash-latest
```

Segredo novo e opcional: `GEMINI_API_KEY`.

## Testes

- Unitários: escolha do pico com áudio sintético; regras de "sem
  flash-forward"; validação e reserva dos textos; pedidos ao Gemini e ao
  Pollinations simulados com `responses`; eventos ASS; grafo do ffmpeg.
- Montagem real com um vídeo gerado pelo ffmpeg (com e sem facecam).
- Verificação final: execução real no GitHub Actions com entrega no
  Telegram, vista pelo dono.
