# Arquitetura

Esta primeira entrega prioriza um ciclo verificável: coletores e `checkupdates` alimentam serviços Python; os serviços persistem dados em SQLite; a correlação determinística alimenta endpoints JSON e a UI estática.

```text
Browser -> HTTP 127.0.0.1:8765 -> API/serviços -> SQLite em XDG_DATA_HOME
                                    |-> checkupdates (consulta)
                                    |-> Discourse / Reddit RSS / GitHub REST / RSS
```

O processo não expõe o servidor na rede local. Os comandos de atualização e snapshot são allowlisted, iniciados somente por botões com confirmação, sem shell e sem `--noconfirm`; os prompts ficam interativos via pseudo-terminal. Os conteúdos externos são texto não confiável, renderizado com escape HTML. Dados e código estão em diretórios distintos; backup do SQLite pode ser feito copiando o arquivo com a aplicação encerrada.

Módulos: `backend/package_manager` consulta pacotes e tamanhos; `backend/collectors` integra fontes com allowlist HTTPS; `backend/analyzer` classifica e correlaciona; `backend/hardware` lê inventário local após ação do usuário; `backend/system_operations` executa somente fluxos fixos de snapshot e atualização sob confirmação explícita, em pseudo-terminal controlador para prompts; `backend/database` mantém esquema e acesso; `backend/api` serve endpoints, assets e logs; `frontend` contém UI estática. O console lateral acompanha saída e progresso da operação; a aba Logs exibe logs do servidor e operações anteriores. A tabela apresenta links e contexto dos relatos correlacionados.

O projeto segue no formato web local, sem Tauri ou etapa de compressão/empacotamento neste roadmap. As futuras fases 3, 5 e 6/7 permanecem abertas, sem implementação ativa planejada. Consulte `PRIVACY_SECURITY.md` para os limites de tráfego externo e leitura local.
