# Canal de factos (MoneyPrinterTurbo)

Dois vídeos por dia, feitos sozinhos no GitHub Actions e entregues no mesmo
Telegram dos clips (a mensagem diz "Vídeo do canal de factos").

**Nicho:** "Real-life Vice City", factos verdadeiros e curiosos sobre Miami e
a Flórida, os sítios reais em que o estado de Leonida do GTA VI se baseia.
Aproveita a curiosidade do lançamento e o Pixabay tem muitos vídeos de Miami
para ilustrar.

## Como funciona

1. `plan.py`: o GitHub Models (grátis) escolhe um tema novo dentro do nicho (sem repetir os
   que estão em `state.json`) e escreve o gancho, o título e a descrição. Se
   falhar, usa o próximo tema de `topics.yaml`.
2. O MoneyPrinterTurbo escreve o texto (a primeira frase é o gancho falado),
   vai buscar vídeos ao Pixabay, grava a voz (Edge, grátis) e põe legendas
   palavra a palavra.
3. `finish.py`: põe o gancho em letras amarelas nos primeiros 3 segundos,
   envia para o Telegram e regista o tema.

Corre às 15h e às 20h (hora de Lisboa no inverno). Para fazer um agora:
Actions → "Factos (MoneyPrinterTurbo)" → Run workflow.

## Chaves (Secrets do repositório)

- Nenhuma chave de IA: usa o GitHub Models com o token do próprio workflow.
- `PIXABAY_API_KEY`: grátis em <https://pixabay.com/api/docs/> (cria conta,
  a chave aparece na própria página, na secção "Parameters", ao lado de
  `key`). O Pexels suspendeu as chaves novas; se tiveres uma,
  `PEXELS_API_KEY` também serve.
- `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`: já estão guardados.

## Aviso importante

Publica estes vídeos num **canal separado** do Wasted Clips (sugestão de
nome: **Real Vice City**). O YouTube não paga a canais de vídeos feitos em
massa com IA, imagens de banco e voz sintética, e avalia o canal inteiro. Se
misturares, arriscas a monetização dos clips. No TikTok o risco é menor, mas
o TikTok também mostra menos conteúdo pouco original.

Sem música de propósito: as músicas que vêm com o MoneyPrinterTurbo podem ter
direitos de autor.

Para mudar de nicho, muda `niche` e `seeds` em `topics.yaml`.
