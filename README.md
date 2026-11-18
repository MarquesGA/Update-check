# Update Watch

**English** | [Português](#portugues)

Update Watch is a local dashboard for checking CachyOS/Arch Linux package updates and reviewing related community reports. I created this personal project through AI-assisted **vibe coding**, then tested and refined it to fit my own workflow and preferences.

> **Local-only application:** the web interface and API listen on `127.0.0.1` and are not exposed to your LAN or a public server. The app has no cloud backend or telemetry. Internet access is used only when you request source synchronization, package checks, or system updates. Those requests send normal network metadata (such as your IP address and User-Agent), but the app does not upload your hardware profile, local history, logs, or installed-package inventory to its issue-monitoring sources.

## Features

- Dashboard with a traffic-light risk summary and the 15 largest pending downloads.
- Full pending-package list, with official repository and AUR checks when `paru` or `yay` is available.
- Community reports from CachyOS, Arch Linux, Mesa, and AMDGPU/ROCm sources, with links to the original reports.
- Local, explainable package-to-report correlation; the results are heuristics, not a guarantee that an update is bug-free.
- Hardware detection on request. The detected hardware stays on this computer.
- Manual snapshots through configured Snapper or Timeshift installations.
- User-confirmed system updates with an operation console, progress indicator, and local operation history.
- SQLite storage that persists separately from the application code.

## Requirements

- Linux, with CachyOS or another Arch-based distribution recommended.
- Python 3.11 or newer. The backend uses the Python standard library; no Python packages need to be installed.
- `checkupdates`, provided by `pacman-contrib`, to check official repository updates.
- Optional: `paru` or `yay` for AUR update checks and updates; `pkexec` for privileged pacman updates; Snapper or Timeshift for snapshots.
- Internet access only for source synchronization, package checks, and package downloads/updates.

## Run locally

From the project directory:

```sh
python -m backend.app
```

Open <http://127.0.0.1:8765> in your browser. Stop the server with `Ctrl+C`. To use another port, set `UPDATE_WATCH_PORT` before starting the app:

```sh
UPDATE_WATCH_PORT=8766 python -m backend.app
```

The service binds to the loopback interface only. Do not change the bind address to `0.0.0.0` or expose this development server to a network.

## Data and privacy

- The SQLite database is stored in `$XDG_DATA_HOME/update-watch/update-watch.sqlite3`, or `~/.local/share/update-watch/update-watch.sqlite3` when `XDG_DATA_HOME` is not set.
- Logs and operation history are stored locally in the user's XDG directories. Updating or replacing the source folder does not remove the database.
- Hardware detection runs only after you request it. Hardware details, logs, history, and installed-package inventory are not sent to issue sources.
- **Sync sources** sends read-only requests to the enabled public feeds/APIs. **Check updates** and **Update system** contact the configured package repositories and, when enabled, the AUR. These network connections are expected for those actions; this app is local-first, not an offline package mirror.
- A GitHub token is optional. If configured through `UPDATE_WATCH_GITHUB_TOKEN`, it is sent only to GitHub's API. Do not commit tokens or other secrets to this repository.
- System updates and snapshots require an explicit action and confirmation. AUR build scripts may run as your user during an AUR update.

See [docs/PRIVACY_SECURITY.md](docs/PRIVACY_SECURITY.md) for the reviewed local reads, network requests, and security boundaries.

## Development and tests

Run the backend tests from the project directory:

```sh
python -m unittest discover -s backend/tests -v
```

The test suite uses local fixtures and does not need live source APIs. For project status and architecture, see [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Project notes

This is an independently developed personal project. It is not affiliated with or endorsed by CachyOS, Arch Linux, AMD, Mesa, or GitHub. The interface and analysis are experimental; review package-manager output and source reports before making system changes.

## License

Update Watch is released under the **MIT License**, a free and permissive open-source license. You may use, copy, modify, and redistribute the project subject to the terms in [LICENSE](LICENSE). The license includes no warranty. Third-party names, services, and source content remain subject to their respective terms.

---

<a id="portugues"></a>

# Update Watch (Português)

O Update Watch é um painel local para consultar atualizações de pacotes do CachyOS/Arch Linux e acompanhar relatos relacionados da comunidade. Desenvolvi este projeto pessoal com **vibe coding** e auxílio de IA, depois validei e aprimorei a aplicação de acordo com minhas preferências e meu fluxo de uso.

> **Aplicação somente local:** a interface e a API escutam em `127.0.0.1` e não ficam expostas à rede local nem a um servidor público. O app não tem backend em nuvem nem telemetria. A internet é usada apenas quando você solicita a sincronização de fontes, a consulta de pacotes ou a atualização do sistema. Essas ações enviam metadados normais de rede (como endereço IP e User-Agent), mas o app não envia seu hardware, histórico local, logs ou inventário de pacotes instalados às fontes de relatos.

## Funcionalidades

- Dashboard com resumo de risco em semáforo e até 15 maiores downloads pendentes.
- Lista completa de pacotes, com consultas aos repositórios oficiais e ao AUR quando `paru` ou `yay` estiver instalado.
- Relatos da comunidade CachyOS, Arch Linux, Mesa e AMDGPU/ROCm, com links para as fontes originais.
- Correlação local, explicável e baseada em nomes de pacotes e relatos. É uma heurística, não uma garantia de que a atualização esteja livre de problemas.
- Detecção de hardware sob solicitação. Os dados detectados permanecem neste computador.
- Criação manual de snapshots com Snapper ou Timeshift configurado.
- Atualização do sistema iniciada e confirmada pelo usuário, com console, indicador de progresso e histórico local.
- Banco SQLite persistente, separado do código da aplicação.

## Requisitos

- Linux; CachyOS ou outra distribuição baseada em Arch é recomendada.
- Python 3.11 ou superior. O backend usa a biblioteca padrão do Python; não é necessário instalar pacotes Python.
- `checkupdates`, fornecido pelo `pacman-contrib`, para consultar atualizações dos repositórios oficiais.
- Opcional: `paru` ou `yay` para consultar e atualizar pacotes do AUR; `pkexec` para atualizações privilegiadas via pacman; Snapper ou Timeshift para snapshots.
- Acesso à internet somente para sincronizar fontes, consultar pacotes e baixar/instalar atualizações.

## Executar localmente

No diretório do projeto:

```sh
python -m backend.app
```

Abra <http://127.0.0.1:8765> no navegador. Encerre o servidor com `Ctrl+C`. Para usar outra porta, defina `UPDATE_WATCH_PORT` antes de iniciar:

```sh
UPDATE_WATCH_PORT=8766 python -m backend.app
```

O serviço fica vinculado somente à interface de loopback. Não altere o endereço para `0.0.0.0` nem exponha este servidor de desenvolvimento na rede.

## Dados e privacidade

- O banco SQLite fica em `$XDG_DATA_HOME/update-watch/update-watch.sqlite3` ou, se `XDG_DATA_HOME` não estiver definido, em `~/.local/share/update-watch/update-watch.sqlite3`.
- Logs e histórico de operações são armazenados localmente nos diretórios XDG do usuário. Atualizar ou substituir a pasta do código não apaga o banco.
- A detecção de hardware só acontece quando solicitada. Dados de hardware, logs, histórico e inventário de pacotes instalados não são enviados às fontes de relatos.
- **Sincronizar fontes** faz requisições somente de leitura aos feeds/APIs públicos habilitados. **Verificar atualizações** e **Atualizar sistema** acessam os repositórios configurados e, quando habilitado, o AUR. Essas conexões são necessárias para as ações; o app é local, mas não é um espelho de pacotes offline.
- O token do GitHub é opcional. Se configurado pela variável `UPDATE_WATCH_GITHUB_TOKEN`, ele é enviado somente à API do GitHub. Não adicione tokens ou outros segredos ao repositório.
- Atualizações e snapshots exigem ação e confirmação explícitas. Scripts de build do AUR podem ser executados como seu usuário durante uma atualização do AUR.

Consulte [docs/PRIVACY_SECURITY.md](docs/PRIVACY_SECURITY.md) para detalhes das leituras locais, conexões externas e limites de segurança revisados.

## Desenvolvimento e testes

Execute os testes do backend a partir do diretório do projeto:

```sh
python -m unittest discover -s backend/tests -v
```

A suíte usa dados locais de teste e não precisa acessar as APIs das fontes. Para ver o estado do projeto e sua arquitetura, consulte [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) e [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Sobre o projeto

Este é um projeto pessoal e independente. Não é afiliado nem endossado pelo CachyOS, Arch Linux, AMD, Mesa ou GitHub. A interface e as análises são experimentais; confira a saída do gerenciador de pacotes e os relatos originais antes de alterar o sistema.

## Licença

O Update Watch é distribuído sob a **Licença MIT**, uma licença livre e permissiva de código aberto. Você pode usar, copiar, modificar e redistribuir o projeto conforme os termos do arquivo [LICENSE](LICENSE). A licença não oferece garantia. Nomes, serviços e conteúdos de terceiros continuam sujeitos aos respectivos termos.
