# Codex Skills

This directory is reserved for repo-managed Codex skills.

Use skills only for specialized reusable workflows that are narrower than the whole project. Keep durable project rules in root `AGENTS.md`, because Codex reads that file automatically before work starts.

Skill folders should live under `skills/` and contain `SKILL.md`, optional `agents/openai.yaml`, and optional `references/`, `scripts/`, or `assets/`.

Codex auto-discovers installed skills from `${CODEX_HOME:-$HOME/.codex}/skills`. Keep repo-specific skills here as source-controlled assets, then copy or symlink a skill into that installed skills directory when you want it globally discoverable.

Example:

```sh
ln -s "$PWD/.codex/skills/my-skill" "${CODEX_HOME:-$HOME/.codex}/skills/my-skill"
```
