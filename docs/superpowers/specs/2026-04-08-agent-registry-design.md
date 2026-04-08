# Agent Registry Design Spec

**Date:** 2026-04-08
**Status:** Draft
**Author:** Yepeng Fan

## Overview

Rename `skills-registry` to `agent-registry` and expand scope from a skill-only registry to a unified registry for **agents** (standalone prompt files with domain knowledge and skill dependencies) and **skills** (slash commands and context skills for Claude Code).

**Goal:** Maintain created agents with domain knowledge and equipped skills in a central registry, installable from anywhere you work.

## Core Concepts

### Agent
A standalone markdown prompt file (`agent.md`) with YAML frontmatter declaring metadata and skill dependencies. Agents carry domain knowledge via reference docs in a `ref/` directory. They can be activated ephemerally via slash command or permanently installed into a project's CLAUDE.md.

### Skill
A package of slash commands (`commands/`) that extend Claude Code's capabilities. Skills are reusable across agents. This is the existing concept from the current `skills-registry`, relocated under a `skills/` directory.

### Relationship
Agents *reference* skills. Skills are independent. An agent's frontmatter declares which skills it needs; the installer resolves and installs them automatically.

## Directory Structure

```
agent-registry/
  agents/
    cit-deck-creator/
      agent.md                  # agent prompt + frontmatter
      ref/                      # domain knowledge docs
        brand-guidelines.md
        slide-patterns.md
    code-reviewer/
      agent.md
      ref/
        review-checklist.md
    devops/
      agent.md
      ref/
        deployment-runbook.md
  skills/
    slides/
      commands/                 # slash commands (generate.md, audit.md)
        generate.md
        audit.md
      ref/                      # skill development reference (not installed)
        slide-audit-script.py
        slide-design-rules.md
        slide-template-patterns.md
      template.pptx
      README.md
  lib/
    parse_frontmatter.py        # Python helper for YAML frontmatter parsing
  install.sh                    # unified installer for agents + skills
  test.sh                       # smoke tests
  README.md
```

**Rules:**
- `agents/<name>/agent.md` is required. Its presence defines an agent package.
- `agents/<name>/ref/` is optional. Contains reference docs the agent prompt can point to.
- `skills/<name>/commands/` contains slash commands, symlinked to `~/.claude/commands/<name>/`.
- `skills/<name>/ref/` is development reference, never installed.
- No nesting beyond one level within `agents/` or `skills/`.

## Agent File Format

Each agent is a single `agent.md` with YAML frontmatter and a markdown body:

```markdown
---
name: cit-deck-creator
description: CI&T branded slide generation and auditing expert
version: 1.0.0
author: Yepeng Fan
tags: [brand, presentations, ci-t]
skills:
  - slides
tools:
  - python-pptx
---

You are a CI&T branded presentation specialist...

## Domain Knowledge

When creating or auditing slides, read the reference docs:
- `ref/brand-guidelines.md` — color palette, typography, logo usage
- `ref/slide-patterns.md` — approved layout patterns

## Behavior

- Always follow CI&T brand rules strictly
- Generate slides using python-pptx
...
```

### Frontmatter Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | yes | string | Identifier (alphanumeric, hyphens, underscores) |
| `description` | yes | string | One-line description shown in `--status` and `--list` output |
| `version` | yes | string | Semver version string (e.g., `1.0.0`) |
| `author` | yes | string | Creator/maintainer name |
| `tags` | no | list | Category tags for filtering/search |
| `skills` | no | list | Skill package names to auto-install |
| `tools` | no | list | External tools/dependencies the agent expects |

### Body

The markdown body is the agent's system prompt. It defines personality, rules, domain knowledge references, and behavior guidelines. This is what gets loaded when the agent is activated.

### Ref Path Resolution

The agent prompt references `ref/` files with relative paths. For ephemeral mode, the install script **copies** (not symlinks) the agent.md to `~/.claude/commands/<name>.md`, prepending a registry path comment:

```markdown
<!-- agent-registry-path: /Users/tedfan/Developer/agent-registry/agents/cit-deck-creator -->
```

This is a deliberate choice over symlinking because:
- We need to inject the registry path for ref resolution without modifying the source file
- Agent prompts change less frequently than skill command code
- Re-running `install.sh` refreshes the copy

Claude resolves `ref/brand-guidelines.md` by reading the path comment and constructing the absolute path to the agent's `ref/` directory in the registry.

## Installation Modes

### Ephemeral Mode (slash command)

```bash
./install.sh                              # install all agents + skills
./install.sh --agent cit-deck-creator     # install one agent + its skill deps
```

Behavior:
1. Parse `agent.md` frontmatter using `lib/parse_frontmatter.py`
2. **Copy** `agents/<name>/agent.md` to `~/.claude/commands/<name>.md` (not symlink — see Ref Path Resolution)
3. Prepend registry path comment to the copied file for ref resolution
4. Read `skills` field from frontmatter
5. For each declared skill, run skill installation (symlink `commands/` to `~/.claude/commands/<skill>/`)
6. Check `tools` field — warn if any declared tool is not found on PATH

Result: typing `/<agent-name>` in any Claude Code session activates the agent. Re-run `install.sh` to pick up changes to agent.md.

### Project Mode

```bash
./install.sh --project cit-deck-creator [target-dir]
```

Behavior:
1. Parse `agent.md` frontmatter
2. Copy agent prompt body (without frontmatter) into `<target-dir>/.claude/CLAUDE.md`
   - If CLAUDE.md exists, append under a `## Agent: <name>` header
3. Copy `ref/` directory to `<target-dir>/.claude/ref/<agent-name>/`
4. Update ref paths in the copied content to point to `.claude/ref/<agent-name>/`
5. Auto-install declared skills (same as ephemeral)

Result: the target project permanently behaves as the agent.

### Skill-Only Installation

```bash
./install.sh --skill slides              # install one skill
./install.sh --skills                     # install all skills only
```

Backward-compatible with the current install behavior. Only installs skill packages, ignores agents.

### Other Commands

```bash
./install.sh --status                     # show install status of all agents + skills
./install.sh --list                       # list available agents and skills with descriptions
./install.sh --uninstall [name]           # remove agent or skill (auto-detects type)
./install.sh --uninstall --agent <name>   # remove agent explicitly
./install.sh --uninstall --skill <name>   # remove skill explicitly
./install.sh --uninstall                  # remove everything
./install.sh --help                       # usage info
```

### Uninstall Behavior

```bash
./install.sh --uninstall cit-deck-creator   # auto-detects type by checking agents/ then skills/
./install.sh --uninstall --agent devops      # explicit type (avoids ambiguity if names collide)
./install.sh --uninstall --skill slides      # explicit type
```

**Name resolution:** When `--uninstall <name>` is called without `--agent`/`--skill`, the script checks `agents/<name>/` first, then `skills/<name>/`. If found in both (name collision), it prints an error and asks the user to specify `--agent` or `--skill`.

- Agent uninstall: remove the copied command file from `~/.claude/commands/`. Declared skills are **kept** (they may be used by other agents or standalone).
- Skill uninstall: remove command symlinks. Warn if any installed agent declares a dependency on the skill.

## Frontmatter Parsing

A Python helper handles YAML frontmatter parsing:

### `lib/parse_frontmatter.py`

- Reads a markdown file, extracts content between `---` delimiters
- Parses YAML using Python's built-in `yaml` module (PyYAML) or a simple key-value parser if PyYAML is unavailable
- Outputs JSON to stdout for shell consumption
- Called by `install.sh` as: `python3 lib/parse_frontmatter.py agents/foo/agent.md`

Example output:
```json
{
  "name": "cit-deck-creator",
  "description": "CI&T branded slide generation and auditing expert",
  "version": "1.0.0",
  "author": "Yepeng Fan",
  "tags": ["brand", "presentations", "ci-t"],
  "skills": ["slides"],
  "tools": ["python-pptx"]
}
```

**Validation:** The parser validates required fields (`name`, `description`, `version`, `author`) and exits non-zero with a clear error if any are missing.

**Dependency:** Python 3 (already required for the slides skill). PyYAML is preferred but the parser falls back to a simple regex-based extractor if unavailable.

## Sample Agents

### 1. `cit-deck-creator`

Migrated from the existing `slides` skill package. Proves the migration path.

- **Prompt:** CI&T brand expert for generating and auditing PowerPoint decks
- **Skills:** `[slides]`
- **Ref docs:** brand guidelines, slide patterns, template patterns (migrated from current `slides/ref/`)
- **Tools:** `[python-pptx]`

### 2. `code-reviewer`

New agent for code review workflows.

- **Prompt:** Code review specialist with knowledge of team conventions, PR standards, and common antipatterns
- **Skills:** none initially
- **Ref docs:** review checklist, coding conventions, PR template
- **Tools:** `[gh]`

### 3. `devops`

New agent for infrastructure and deployment work.

- **Prompt:** Infrastructure and deployment specialist
- **Skills:** none initially
- **Ref docs:** deployment runbook, CI/CD pipeline reference, cloud architecture notes
- **Tools:** `[docker, kubectl, terraform]`

For `code-reviewer` and `devops`, the ref docs will be created as templates with placeholder sections. The user fills in actual domain knowledge.

## Testing Strategy

Extend `test.sh` with tests for the new agent functionality:

### Agent Tests
- Install an agent → verify symlink created at `~/.claude/commands/<name>.md`
- Verify skill dependencies auto-installed alongside the agent
- Project mode → verify CLAUDE.md created/appended in target dir, `ref/` copied
- Uninstall agent → verify symlinks removed, skills kept
- Name validation (same allowlist: `^[a-zA-Z0-9_-]+$`)

### Skill Tests
- Same as current (install, status, uninstall, validation) with updated paths under `skills/`

### Frontmatter Parsing Tests
- Valid frontmatter parsed correctly (all fields extracted)
- Missing required fields → non-zero exit with clear error message
- Invalid skill dependency name → warning
- Malformed YAML → clear error

### Integration Tests
- Install agent with skill dependency → both installed
- Uninstall skill that an agent depends on → warning printed
- `--list` shows all agents and skills with descriptions
- `--status` shows correct link status for both types

## Migration Plan

Moving from `skills-registry` to `agent-registry`:

1. **Rename repo** — `skills-registry` → `agent-registry`
2. **Move existing skill** — `slides/` → `skills/slides/`
3. **Create agent from skill** — extract domain knowledge from `slides/ref/` into `agents/cit-deck-creator/ref/`, write `agent.md`
4. **Add lib/** — create `lib/parse_frontmatter.py`
5. **Rewrite install.sh** — support agents, skills, ephemeral + project modes, frontmatter parsing
6. **Update test.sh** — add agent tests, update skill test paths
7. **Create sample agents** — `code-reviewer` and `devops` with template ref docs
8. **Update README.md** — new name, updated structure, usage docs
9. **Update .gitignore** — any new patterns needed

## Out of Scope

- Remote registry / package manager (e.g., `agent-registry pull <url>`) — future work
- Agent versioning/update mechanism beyond the `version` field — future work
- MCP server packaging for agents — decided against in design phase
- Agent-to-agent composition (one agent delegating to another) — future work
- GUI or web interface for browsing agents — future work
