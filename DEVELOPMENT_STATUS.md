# Estado do desenvolvimento

Atualizado em 2026-11-12.

## Concluído nesta entrega

- Base executável sem pacotes Python de terceiros; HTTP restrito a loopback.
- Banco SQLite persistente sob XDG, migração inicial e tabelas para fontes, publicações, pacotes, análises e histórico.
- Consulta segura de `checkupdates`; sem ações administrativas.
- Coletores Discourse, Reddit RSS e GitHub API, além de RSS/Atom genérico; deduplicação, estados/erros por fonte.
- Correlação local explicável, severidade e dashboard conectado a dados da API.
- Interface web adaptável com dashboard, pacotes, feed, análise, histórico e configurações.
- Testes de parsing, correlação, armazenamento/deduplicação e limites do gerenciador de pacotes.
- Consulta opcional AUR por `paru -Qua`/`yay -Qua`, sem operação de instalação.
- Detecção de hardware local sob ação explícita do usuário na tela Configurações.
- Estado de issues salvo junto às publicações; issues concluídas pelo GitHub ficam separadas dos relatos abertos na análise.
- Fonte dedicada para CachyOS/distribution, Mesa (GitLab) e AMDGPU (ROCm GitHub).
- Tamanho de download consultado localmente com `pacman -Si`; dashboard limita a 15 maiores, mantendo listagem completa em Pacotes.
- Semáforo do dashboard: crítico vermelho, atenção amarelo/laranja, normal verde. Crítico exige cinco relatos recentes correlacionados em pelo menos duas fontes.
- Snapshot manual via Snapper/Timeshift e atualização completa via paru/yay ou pacman, com confirmação explícita, autenticação do sistema e respostas interativas no painel.
- Console fixo à direita com saída/progresso somente da operação atual ou última; logs ficam em uma aba própria.
- Durante a atualização, o console se expande acima da lista de maiores downloads; prompts de senha usam campo mascarado e a verificação de pacotes mostra progresso.
- Após concluir uma atualização, o app consulta novamente os pacotes e remove da lista entradas obsoletas quando a consulta termina sem erro. Erros de fontes mostram o detalhe retornado pelo servidor.
- O coletor GitHub tolera issues sem corpo/autor, como os publicados em alguns repositórios AMDGPU.
- Pacotes ordenados por risco (crítico, atenção, informativo, normal); relatos expandem inline com resumo, status, fonte e link original.
- Histórico agrega início/resultado de snapshot e update; a aba Logs mostra separadamente os registros do servidor e operações.
- Revisão documentada dos fluxos locais, chamadas externas e dados enviados em `docs/PRIVACY_SECURITY.md`.

## Pendências do roadmap

- Fase 1 (Tauri/React/desktop nativo): descartada; a versão web local atende ao formato desejado.
- Fase 2: consulta AUR, leitura de hardware e tamanho de download concluídos. Dependências permanecem em aberto.
- Fase 3 (agendamento, fontes configuráveis completas e comentários): em aberto.
- Fase 4: identificação de issues GitHub concluídas implementada; validar se uma versão corretiva está nos pacotes pendentes, independência de relatos e categorias editáveis permanecem em aberto. Fontes Mesa e AMDGPU adicionadas nesta versão.
- Fase 5 (IA local): em aberto.
- Fases 6/7 (notificações, exportação, instalador/empacotamento e distribuição): em aberto.

## Limitações conhecidas

- A UI é servida por HTTP local, conforme o formato definido para o projeto.
- A API está protegida por bind em `127.0.0.1`; não há autenticação de sessão. Não deve ser alterado para bind público.
- Coleta externa depende de rede, disponibilidade das APIs e respectivos limites.
- A classificação e correlação são heurísticas locais; não representam garantia de segurança da atualização.
- Sem IA, token ou notificações nativas; atualização de pacotes fica disponível somente após confirmação explícita no app.
- Snapshot exige Snapper com configuração `root` ou Timeshift configurado. Nenhum snapshot ou atualização foi executado nesta validação.
- A ação de atualização usa helper AUR disponível (`paru`/`yay`) ou `pkexec pacman -Syu`, sem `--noconfirm`; o usuário responde aos prompts no painel.
- Snapper/Timeshift não informa progresso percentual consistente; o painel usa indicador indeterminado durante essas operações e mostra 100% ao terminar. Na instalação de pacotes, exibe contagem quando o gerenciador a fornece.

## Testes

Hardware verificado neste CachyOS de desenvolvimento: AMD Ryzen 5 5600X (6 núcleos/12 threads), 31,3 GiB de memória utilizável (32 GiB instalados), AMD Radeon RX 6950 XT com `amdgpu`, kernel `7.3.3-1-cachyos`, sessão KDE/Wayland e Btrfs. O detector do app lê esses dados sob solicitação e não os transmite.

Resultado desta atualização: 25 testes passaram (`python -m unittest discover -s backend/tests -q`); `python -m compileall -q backend` passou. `deno check --no-config frontend/app.js` passou. Os testes incluem issue GitHub sem corpo, atualização bem-sucedida da lista sem itens, TTY controlador, resposta de senha sem shell, validação Host/Origin e allowlist de URLs externas. Nenhum update ou snapshot real foi executado.
