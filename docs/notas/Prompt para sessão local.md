Estou a continuar um projeto chamado Clipper GTA VI. O código está no repositório público https://github.com/bieis-stack/gta6-clipper (já tenho sessão iniciada no GitHub neste computador). Começa por ler `docs/HANDOFF.md` e `docs/notas/Clipper GTA VI.md` desse repositório; têm o contexto completo.

Preciso que faças três coisas neste computador, usando o controlo do computador quando for preciso. Fala comigo em português de Portugal, em linguagem simples, e diz-me antes de cada passo o que vais fazer.

1. **Guardar a nota no meu Obsidian.** Copia `docs/notas/Clipper GTA VI.md` do repositório para o meu cofre do Obsidian, na pasta `OBSIDIAN CLAUDE`. Se já existir uma nota com esse nome, substitui-a.

2. **Criar o bot do Telegram e guardar as chaves no GitHub.**
   - No Telegram Desktop, fala com o **@BotFather** (o que tem o visto azul), envia `/newbot`, usa o nome `Clipper GTA` e um nome de utilizador livre que acabe em `bot`.
   - Abre a ligação `t.me/...` do bot novo e carrega em **Iniciar**, senão o bot não me consegue escrever.
   - Fala com o **@userinfobot** e carrega em **Iniciar** para obter o meu Id.
   - Guarda dois *repository secrets* em https://github.com/bieis-stack/gta6-clipper/settings/secrets/actions (separador **Secrets**, não *Variables*): `TELEGRAM_BOT_TOKEN` com o token do BotFather, e `TELEGRAM_CHAT_ID` com o meu Id. Se o `gh` estiver instalado e com sessão iniciada, podes usar `gh secret set` em vez do browser.
   - Nunca escrevas o token nem o Id na conversa nem em nenhum ficheiro. Diz-me só que ficaram guardados.

3. **Apagar o ramo `ensaio`** do repositório (tem fotogramas de uma stream que não devem ficar públicos): em https://github.com/bieis-stack/gta6-clipper/branches, ou com `git push origin --delete ensaio`.

Depois disso, testa a entrega: em https://github.com/bieis-stack/gta6-clipper/actions/workflows/clipper.yml carrega em **Run workflow**, deixa **dry_run** desmarcado e escreve `Minecraft` em **game_name**. Espera que termine e diz-me o resultado; eu confirmo se os vídeos me chegaram ao Telegram. Se aparecer `candidatos=0`, repete com outro jogo que algum dos streamers da lista esteja a jogar nesse dia.

Não publiques clips em nenhum sítio público e não alteres o código sem me perguntar.
