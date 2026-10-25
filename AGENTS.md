# BookRoomLog — Regras e Diretrizes do Projeto

Este arquivo define as convenções e padrões arquiteturais a seguir neste repositório. O projeto nasceu do
GameRoomLog (`../GameRoomLog-main`) e mantém a mesma arquitetura e os mesmos padrões.

## 1. Padrões de Código e Arquitetura
- **Backend (FastAPI):** Mantenha a separação em camadas: rotas em `backend/app/api/v1/endpoints/`, regras de negócio em `backend/app/services/` e schemas em `backend/app/schemas/`. Nunca faça queries SQL diretamente dentro dos endpoints da API.
- **Regras de status ficam no backend** (`BookService._apply_status_rules`): nota e data de término só para `Lido` (sem data, vale o dia de hoje; o ano do Anuário vem dela), progresso só para `Lendo`, posição na fila só para `Próximo` (a fila é sempre renumerada de 1 a N). O app não calcula tempo de leitura nem guarda data de início.
- **Categorias por nome:** livros recebem `authors`, `genres`, `publisher` e `series` como nomes; o backend reaproveita (sem diferenciar maiúsculas) ou cria. Autores e gêneros guardam a ordem (`position`).
- **Releituras** são registros novos ligados ao original (`reread_of_id` aponta sempre para a 1ª leitura; `read_number` ≥ 2).
- **Frontend (PySide6):** O frontend não acessa o banco de dados diretamente; todas as operações passam pelo `ApiClient` (`frontend_desktop/api_client/client.py`). Chamadas de rede rodam fora da thread da UI (`workers.run_async`).
- **UI Performance:** Mantenha as mutações de interface in-place (`insert_book`, `update_book`, `remove_book`, `MainWindow.apply_book_mutation`) evitando recarregamentos totais (`refresh_all_data`) desnecessários. Mudanças que mexem na fila de Próximos recarregam só a fila (`refresh_next_queue`).
- **Sinais globais** (`cover_loader.loaded`, preferências) devem ser assinados com `cover_loader.subscribe` / `preferences.subscribe` (referência fraca): o widget pode ser destruído antes de a capa chegar.
- **Visibilidade de Campos:** No `BookDialog`, use `setVisible(False)` para campos condicionais irrelevantes ao status selecionado.
- **Porta da API:** 8010 (o GameRoomLog usa a 8000; os dois apps podem ficar abertos juntos).

## 2. Testes e Cobertura Obrigatória (Workflow de Funcionalidades)
- Qualquer nova funcionalidade ou refatoração no backend ou frontend **DEVE** ter cobertura de testes automatizados criada antes de ser finalizada, seguindo a skill `.claude/skills/ensure-test-coverage/SKILL.md`.
- Teste sempre caminhos felizes e casos de erro (404/422/campos vazios).
- Testes do frontend: a fixture `backend` coloca a API real (banco em memória) atrás do `api_client`; `sync_async` roda o `run_async` de forma síncrona. Chamadas a APIs externas (Google Books / Open Library) são simuladas com `respx`.
- O pré-commit hook do Git (`scripts/install-hooks.sh`) roda ruff e pytest e bloqueia o commit se falharem. Cobertura mínima no CI: 85%.

## 3. Lançamento de Novas Versões
- Ao lançar uma nova versão, utilize o workflow definido na skill `.claude/skills/release-version/SKILL.md` ou execute o helper `.claude/skills/release-version/scripts/release.py <VERSAO>`.

## 4. Publicação no GitHub e Controle de Versão (Git Push)
- **Sempre pelo GitHub CLI (`gh`):** toda operação no GitHub (push, PRs, issues, releases, Actions, consultas) segue a skill `.claude/skills/github-cli/SKILL.md`.
- **Aprovação Prévia Obrigatória:** NUNCA execute `git push` (de branches ou tags) sem antes avisar o usuário, exibir claramente o resumo dos commits, tags e alterações que serão enviadas, e solicitar a aprovação explícita dele.
