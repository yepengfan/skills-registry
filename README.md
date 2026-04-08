# agent-registry

A unified registry for Claude Code **agents** and **skills**, managed in one place and installable from anywhere you work.

## Concepts

- **Agent** — A standalone prompt file (`agent.md`) with domain knowledge and skill dependencies. Agents can be activated as slash commands or installed into a project's CLAUDE.md.
- **Skill** — A package of slash commands that extend Claude Code's capabilities. Skills are reusable across agents.

## Structure

```
agent-registry/
  agents/
    <agent-name>/
      agent.md          # Agent prompt + YAML frontmatter
      ref/              # Domain knowledge docs
  skills/
    <skill-name>/
      commands/          # Slash commands -> ~/.claude/commands/<skill>/
      ref/              # Development reference (not installed)
  lib/
    parse_frontmatter.py # Frontmatter parser
  install.sh
  test.sh
```

## Available Agents

| Agent | Description | Skills | Tools |
|-------|-------------|--------|-------|
| [cit-deck-creator](agents/cit-deck-creator/) | CI&T branded slide generation and auditing | slides | python-pptx |
| [code-reviewer](agents/code-reviewer/) | Code review for team conventions and quality | — | gh |
| [devops](agents/devops/) | Infrastructure and deployment specialist | — | docker, kubectl, terraform |

## Available Skills

| Skill | Description |
|-------|-------------|
| [slides](skills/slides/) | CI&T branded slide generation and auditing commands |

## Usage

### Install everything

```bash
./install.sh
```

### Install a single agent (+ its skill dependencies)

```bash
./install.sh --agent cit-deck-creator
```

### Install a single skill

```bash
./install.sh --skill slides
```

### Install an agent into a project

```bash
./install.sh --project devops ~/my-project
```

This copies the agent prompt into `~/my-project/.claude/CLAUDE.md` and the reference docs into `~/my-project/.claude/ref/devops/`.

### Check status

```bash
./install.sh --status
```

### List available agents and skills

```bash
./install.sh --list
```

### Uninstall

```bash
./install.sh --uninstall cit-deck-creator   # auto-detects type
./install.sh --uninstall --agent devops      # explicit
./install.sh --uninstall --skill slides      # explicit
./install.sh --uninstall                     # remove all
```

### Run tests

```bash
./test.sh
```

## Agent File Format

```markdown
---
name: my-agent
description: What this agent does
version: 1.0.0
author: Your Name
tags: [category, tags]
skills:
  - skill-name
tools:
  - external-tool
---

Agent system prompt goes here...
```

| Field | Required | Description |
|-------|----------|-------------|
| name | yes | Identifier (alphanumeric, hyphens, underscores) |
| description | yes | One-line description |
| version | yes | Semver version |
| author | yes | Creator/maintainer |
| tags | no | Category tags |
| skills | no | Skill dependencies (auto-installed) |
| tools | no | External tools (warnings if missing) |

## Adding a new agent

1. Create `agents/<name>/` with an `agent.md` file
2. Add `ref/` docs with domain knowledge
3. List skill dependencies in frontmatter
4. Run `./install.sh --agent <name>` to install

## Adding a new skill

1. Create `skills/<name>/commands/` with `.md` command files
2. Add a `README.md` describing the skill
3. Run `./install.sh --skill <name>` to install
