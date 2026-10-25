---
name: github-cli
description: >-
  Regra do projeto para qualquer operação no GitHub: sempre usar o GitHub CLI (`gh`). Use esta skill
  sempre que for publicar (push), criar ou consultar o repositório, abrir/ver pull requests, issues,
  releases, tags publicadas, execuções do GitHub Actions ou qualquer outra coisa em
  github.com/FabricioPereira008/BookRoomLog.
---

# GitHub sempre pelo GitHub CLI (BookRoomLog)

Toda interação com o GitHub neste projeto passa pelo **GitHub CLI (`gh`)**. Não use a interface web,
chamadas `curl` à API, tokens colados em URLs nem outros clientes.

- Repositório: `FabricioPereira008/BookRoomLog` (branch padrão `main`)
- Conta: `FabricioPereira008`, autenticada no `gh` (protocolo HTTPS)

## 1. Antes de qualquer operação

```bash
gh auth status          # precisa mostrar a conta FabricioPereira008 logada
gh auth setup-git       # o git passa a usar as credenciais do gh no push/pull/fetch por HTTPS
```

Se não estiver logado, peça ao usuário para rodar `! gh auth login` (é interativo).

## 2. Operações e o comando certo

| Operação | Comando |
|---|---|
| Ver o repositório | `gh repo view FabricioPereira008/BookRoomLog` |
| Ligar o repositório local ao remoto | `git remote add origin "$(gh repo view FabricioPereira008/BookRoomLog --json url -q .url).git"` |
| Clonar | `gh repo clone FabricioPereira008/BookRoomLog` |
| Publicar commits (push) | `gh auth setup-git` e depois `git push origin <branch>` |
| Pull request | `gh pr create`, `gh pr list`, `gh pr view`, `gh pr checks`, `gh pr merge` |
| Issues | `gh issue list`, `gh issue create`, `gh issue view` |
| CI / builds (GitHub Actions) | `gh run list`, `gh run watch`, `gh run view --log-failed`, `gh workflow run build-release.yml` |
| Releases | `gh release list`, `gh release view vX.Y.Z` (o workflow `build-release.yml` cria a release ao receber a tag) |
| Qualquer outra consulta | `gh api repos/FabricioPereira008/BookRoomLog/...` |

O `git push` em si é do git, mas sempre com as credenciais configuradas pelo `gh auth setup-git`. Não
grave tokens no remote (`https://<token>@github.com/...`).

## 3. Regras de segurança (valem junto com o AGENTS.md)

- **Aprovação antes de publicar:** nunca faça `git push` (branch ou tag), `gh pr merge`, `gh release create`
  ou `gh repo edit` sem mostrar antes o resumo (commits, tags e arquivos) e ter a aprovação explícita do usuário.
- **Sem force push** (`--force`, `--force-with-lease`) a menos que o usuário peça exatamente isso para aquele caso.
- **Histórico divergente:** se o remoto tiver commits que o local não tem, mostre quais são
  (`gh api repos/FabricioPereira008/BookRoomLog/commits`) e integre com `git pull`/merge em vez de sobrescrever.
- **Menções:** em PRs, issues e comentários, só escreva `@usuario` para quem deve ser notificado de verdade.
- Depois de um push, acompanhe o CI com `gh run list --limit 3` / `gh run watch` e informe o resultado.
