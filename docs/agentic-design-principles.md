# Agentic Design Principles

> Reference document for designing and evolving multi-agent workflows.
> Update when new failure patterns are observed or principles need revision.

## 1. Single Responsibility

Each agent has ONE job. If an agent does two things, split it.

**Rationale:** The pr-reviewer was overloaded with code review and Figma verification. Splitting into pr-code and pr-design made each focused and manageable.

## 2. Bounded Work Per Agent

No agent should receive unbounded input. If input scales with PR size (files, diff lines), the coordinator must batch it.

**Rationale:** A single reviewer can't handle a 2000-line diff. The coordinator batches files into ~500 diff-line chunks so each reviewer stays within context budget.

**Rule:** Target ≤500 diff lines per code review agent. If a single file exceeds 500 lines, it gets its own batch.

## 3. Constrained Reading Protocol

Every agent that reads files must have explicit rules: what tool to use, max tool calls per file, no redundant reads.

**Rules:**
- Never fetch the full monolithic diff — process one file at a time
- Use the Read tool for file context — not `gh api`, `git show`, or `cat`
- Max 3 tool calls per changed file (1 for diff, up to 2 for context)
- Analyze as you read — don't queue all reading before analysis
- Never read the same content twice via a different command
- Never pipe through head/tail/sed — use Read with offset/limit

**Rationale:** Without constraints, the reviewer wasted 70 of 80 tool calls reading the same content in different ways.

## 4. Verify, Don't Trust

Every claim by a sub-agent must be independently verified by the caller.

| Claim | Verify by |
|---|---|
| "Tests pass" | Run test suite, check output |
| "Committed and pushed" | `git log --oneline -1` for the expected SHA |
| "N issues found" | Count the actual JSON array length |
| "Comments posted" | `gh pr view --comments` |

**Rationale:** The fixer reported "committed and pushed" but the commit didn't exist.

## 5. Recover on Verification Failure

Verification failure must trigger a recovery path, not just a report.

**Recovery protocol:**
1. Log the discrepancy (what was claimed vs what was found)
2. Retry with a different dispatch method (general-purpose if subagent_type failed)
3. If retry also fails, mark as unfixed and report
4. Never silently accept the sub-agent's version

**Rationale:** The first fixer failed silently. The orchestrator caught it via `git log` but had no automatic retry.

## 6. Prefer General-Purpose Dispatch for Write Operations

When an agent needs to edit files, commit, or push, dispatch as a general-purpose agent (no `subagent_type`). Reserve `subagent_type` for read-only analysis.

**Rules:**
- Fixer agents: always dispatch as general-purpose
- Code review agents: `subagent_type` is fine (read-only + GH API comments)
- Design review agents: `subagent_type` is fine (read-only + GH API comments)

**Rationale:** General-purpose agents' file operations persist reliably. Named sub-agents may run in sandboxed contexts where writes don't persist.

## 7. Deterministic Scripts Over LLM Judgment

For reproducible operations (diffing, mapping, tolerance checking), use scripts. LLM agents invoke scripts, not re-implement the logic.

**Examples:**
- `design-diff.js` — element mapping, tolerance comparison, fix hint generation
- `figma-extract.js` — structured Figma inventory extraction
- `dom-extract.js` — computed style extraction from rendered DOM

**Rationale:** If an LLM re-implemented diffing logic, results would be inconsistent across runs. Scripts are deterministic and testable.

## 8. Three-Layer Separation

```
Orchestrator (Opus)  — decides: loop control, gate evaluation, exit
Coordinator (Sonnet) — dispatches: batch computation, parallel fan-out, result merge
Agent (Sonnet)       — executes: focused work on bounded scope
```

**Rules:**
- Orchestrators never read file content or diffs
- Coordinators never make gate/exit decisions
- Agents never dispatch other agents

**Rationale:** Mixing dispatch logic into the orchestrator bloats its context. Mixing decisions into agents makes them fragile.

## 9. Stateless Agents, Stateful Orchestrators

Agents receive everything they need in the prompt. They don't read prior round results or track accumulated state. The orchestrator owns state.

**Orchestrator owns:**
- Consecutive clean count
- Prior round suggestions
- Cached Figma inventories
- Environmental blocker tracking

**Agents receive:**
- Their scope (file list, screen list)
- Criteria definitions
- Prior suggestions (injected by orchestrator, not self-discovered)

**Rationale:** Stateless agents produce consistent results. If the design reviewer tracked prior results, it would bias toward previously-failing screens.

## 10. Explicit I/O Contracts

Every agent declares its input shape and output shape in frontmatter. The caller validates outputs match the contract.

**Frontmatter `interface` field:**
```yaml
interface:
  input: What the agent receives
  output: What the agent returns (format, structure)
```

**Validation rules:**
- Output must be valid JSON when JSON is expected
- All required fields must be present
- Array lengths must match claimed counts
- If output is invalid, report error — don't fabricate results

**Rationale:** When a reviewer returns invalid JSON, the orchestrator needs to know what valid JSON looks like to detect the failure.

---

## Principle Application Matrix

| Principle | Orchestrator | Coordinator | Code Reviewer | Design Reviewer | Fixer |
|---|:---:|:---:|:---:|:---:|:---:|
| 1. Single Responsibility | Loop control | Batch + merge | Code quality | Design fidelity | Apply fixes |
| 2. Bounded Work | N/A | Batches files | ≤500 diff lines | All screens | Only must-fix list |
| 3. Reading Protocol | No file reading | Diff stat only | Max 3 calls/file | Scripts do extraction | Issue list + targets |
| 4. Verify Don't Trust | Verifies all | Verifies JSON | N/A (leaf) | N/A (leaf) | N/A (leaf) |
| 5. Recover on Failure | Retry fixer | Report failed batches | N/A | N/A | N/A |
| 6. GP for writes | N/A | N/A | GH API only | GH API only | **General-purpose** |
| 7. Scripts over LLM | N/A | N/A | N/A | design-diff.js | N/A |
| 8. Three layers | Decides | Dispatches | Executes | Executes | Executes |
| 9. Stateless | Owns state | Stateless | Stateless | Stateless | Stateless |
| 10. I/O Contracts | Validates | Unified JSON | Issues JSON | Issues JSON | Fixed/unfixed JSON |

---

## Observed Failures Log

Track failures here to inform principle updates.

| Date | Failure | Root Cause | Principle Violated | Fix Applied |
|---|---|---|---|---|
| 2026-04-17 | Fixer commit didn't persist | subagent_type dispatch sandboxed writes | #6 (GP for writes) | Re-dispatched as general-purpose agent |
| 2026-04-17 | Reviewer exhausted context on reading | No reading constraints, 80+ redundant tool calls | #2 (bounded), #3 (reading protocol) | Added per-file reading protocol to pr-code |
| 2026-04-17 | Design mismatches missed across screens | Single reviewer guessed which screens to check | #1 (single responsibility), #2 (bounded) | Split into pr-design with all-screen sweep |
| 2026-04-17 | Unmatched Figma elements not counted as failures | design-diff.js treated them as informational | #7 (scripts over LLM) | Added presence mismatches to design-diff.js |
