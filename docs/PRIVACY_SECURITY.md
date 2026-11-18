# Privacidade e segurança — revisão do app local

Revisão estática dos fluxos de rede, leitura local, armazenamento e execução de comandos, atualizada em 2026-11-12.

## O que permanece local

- A interface, o backend, o console e os endpoints JSON são servidos em `127.0.0.1`; o servidor não escuta na rede local.
- Hardware é lido somente quando solicitado. O detector lê `/proc/cpuinfo`, `/proc/meminfo`, `/etc/os-release`, saída de `lscpu`/`lspci`/`findmnt` e variáveis XDG da sessão. Não lê hostname, identificadores de máquina, números de série, lista de arquivos pessoais ou endereços de rede, e o resultado não é incluído em nenhuma requisição externa.
- SQLite, histórico, detalhes de operações e logs ficam nos diretórios XDG do usuário. Não há envio automático de logs, perfil de hardware ou histórico.
- A interface não carrega analytics, fontes web ou scripts de terceiros.
- O backend valida Host/Origin e `Sec-Fetch-Site` contra o loopback/porta local; fontes HTTP são limitadas a uma allowlist HTTPS, incluindo validação de redirects. Isso reduz DNS rebinding, CSRF e SSRF por URL de fonte adulterada.
- Snapshot usa Snapper/Timeshift localmente. Nenhum snapshot é criado em segundo plano.

## O que usa a rede

- O botão **Sincronizar fontes** faz requisições HTTP GET para as fontes habilitadas: CachyOS Discourse/GitHub, Reddit RSS, Arch News, Mesa GitLab e ROCm/amdgpu GitHub. As respostas são armazenadas localmente. A requisição contém User-Agent e metadados normais de rede (como IP de origem); não inclui hardware, histórico, logs ou pacotes instalados.
- Se `UPDATE_WATCH_GITHUB_TOKEN` estiver definido, o token é enviado somente à API GitHub pelo header de autenticação.
- **Verificar atualizações** usa `checkupdates`, que consulta os repositórios configurados, `paru/yay -Qua`, que consulta o AUR, e `pacman -Si`, que lê tamanhos no banco de sincronização local. Essas ferramentas podem acessar servidores de pacote para suas consultas; não enviam o inventário de hardware.
- **Atualizar sistema** necessariamente baixa pacotes e/ou scripts dos repositórios configurados. Com `paru`/`yay`, scripts de build do AUR podem executar como o usuário durante a instalação. A ação exige confirmação explícita; o app não usa `--noconfirm`.

## Limites de segurança verificados

- O backend não usa shell para comandos do sistema. Os comandos de update e snapshot vêm de uma lista fixa; entrada da publicação/feed não é usada como argumento de comando.
- Atualização e snapshot exigem confirmação na UI e na API. Prompts são entregues por pseudo-terminal controlador.
- Respostas do painel são enviadas diretamente ao pseudo-terminal do processo fixo, sem shell. O campo aceita senhas e respostas de até 256 caracteres, mas bloqueia quebras de linha e caracteres de controle; senhas são mascaradas na interface.
- Conteúdo de fontes é escapado antes de renderizar; links externos usam `noopener`.
- O app não executa um modelo de IA nem envia dados a serviços de IA.

## Escopo desta validação

Esta é uma revisão de código e dos caminhos de execução, sem captura de tráfego. Consultas de fontes e gerenciadores de pacotes fazem conexões externas quando o usuário solicita sincronização, verificação ou atualização. Nenhum inventário do dispositivo é incluído nesses pedidos.
