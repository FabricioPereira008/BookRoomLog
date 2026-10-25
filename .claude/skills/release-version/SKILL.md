---
name: release-version
description: >-
  Executes the release process for new versions of BookRoomLog. Use this skill whenever
  the user asks to release a new version (e.g. "lance a versão 0.2.3", "crie uma nova versão",
  "bump version", "gerar release"). It runs all tests, updates version strings in all
  files, updates CHANGELOG.md, and creates the git commit and tag.
---

# Release Version Workflow (BookRoomLog)

This skill automates the end-to-end release process for new versions of the BookRoomLog application.

## Workflow Overview

When releasing a new version, the agent must execute the following sequence:

1. **Pre-flight Check**: Run the complete automated test suite (`pytest`) to ensure no existing regressions.
2. **Version Update**: A versão vive em um único lugar, `app_version.py` (`__version__`). Backend, frontend e testes importam dela, então só esse arquivo muda.
3. **Changelog Generation**: Add a structured release entry in `CHANGELOG.md` adhering to the *Keep a Changelog* format.
4. **Post-update Test Run**: Re-run the test suite to ensure the updated version assertions pass.
5. **Git Commit & Tag**: Create an annotated git commit `chore(release): bump version to v<VERSION>` and a tag `v<VERSION>`.

---

## Execution Options

### Option A: Using the Automated Release Helper (Recommended)

Run the release script directly from the project root:

```bash
./venv/bin/python .claude/skills/release-version/scripts/release.py <NEW_VERSION> ["Release notes in Markdown"]
```

**Example:**
```bash
./venv/bin/python .claude/skills/release-version/scripts/release.py 0.2.3 "### Adicionado\n- Nova tela de estatísticas.\n\n### Corrigido\n- Bug no scroll da lista."
```

---

### Option B: Manual Execution Steps

If running manually step-by-step:

1. **Run tests:**
   ```bash
   ./venv/bin/pytest -v
   ```
2. **Edit `__version__` in `app_version.py`.**
3. **Update `CHANGELOG.md`:**
   Insert `## [<NEW_VERSION>] - YYYY-MM-DD` at the top of the version list.
4. **Run tests again:**
   ```bash
   ./venv/bin/pytest -v
   ```
5. **Create Git commit and tag:**
   ```bash
   git add CHANGELOG.md app_version.py
   git commit -m "chore(release): bump version to v<NEW_VERSION>"
   git tag -a v<NEW_VERSION> -m "Release v<NEW_VERSION>"
   ```

## Importante

A skill cria apenas commit e tag **locais**. Nunca execute `git push` (branch ou tag) sem mostrar ao usuário o resumo do que será enviado e obter aprovação explícita (regra do `AGENTS.md`). O push da tag dispara o build no GitHub Actions.
