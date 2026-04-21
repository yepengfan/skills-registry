"""SDK wrappers for reviewer and fixer agents."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage, AssistantMessage,
)

from .schema import Finding, ReviewOutput, Severity
from .progress import print_sdk_message, C


def _load_agent_prompt(path: Path) -> str:
    """Load an agent.md file, strip YAML frontmatter, return the body."""
    raw = path.read_text()
    match = re.match(r"^---\n[\s\S]*?\n---\n([\s\S]*)$", raw)
    return match.group(1).strip() if match else raw.strip()


JSON_OUTPUT_INSTRUCTIONS = """
Output ONLY a JSON object matching this exact schema — no markdown fences, no prose before or after:

{
  "summary": "One-sentence overall assessment",
  "findings": [
    {
      "id": "F-001",
      "severity": "must-fix",
      "category": "correctness",
      "claim": "One-sentence issue description",
      "reasoning": "Why this is a problem",
      "file": "path/to/file.ts",
      "line_start": 42,
      "line_end": 48,
      "quoted_code": "verbatim lines from the file",
      "suggested_fix": "concrete fix"
    }
  ]
}

severity must be "must-fix" or "nice-to-have".
category must be one of: correctness, security, style, testing, other.
"""


def _build_reviewer_prompt(diff: str, gates_summary: str, round_num: int,
                            agent_prompt: str) -> str:
    return f"""{agent_prompt}

{JSON_OUTPUT_INSTRUCTIONS}

---

DETERMINISTIC FACTS (from actual test/lint/build execution — accept these as given):
{gates_summary}

Round: {round_num}

PR diff:
```diff
{diff}
```"""


def _build_fixer_prompt(findings: list[Finding], round_num: int,
                         agent_prompt: str) -> str:
    findings_json = json.dumps([f.model_dump() for f in findings], indent=2)
    return f"""{agent_prompt}

---

Round: {round_num}

Findings:
{findings_json}"""


def _extract_json(text: str) -> dict | None:
    """Extract JSON from text response — handles markdown fences and surrounding prose."""
    if not text:
        return None

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in text
    brace_start = text.find("{")
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start : i + 1])
                    except json.JSONDecodeError:
                        break

    return None


async def _run_query(prompt: str, options: ClaudeAgentOptions, phase: str) -> tuple[ResultMessage, str]:
    """Run an SDK query, stream progress, return (result_message, last_assistant_text)."""
    start = time.monotonic()
    result_msg = None
    last_text = ""
    msg_count = 0
    last_heartbeat = start

    try:
        async for message in query(prompt=prompt, options=options):
            msg_count += 1
            now = time.monotonic()

            # Heartbeat every 30s
            if now - last_heartbeat >= 30:
                elapsed = now - start
                print(f"{C.DIM}  [{phase}] still working... {elapsed:.0f}s elapsed, {msg_count} messages{C.RESET}", flush=True)
                last_heartbeat = now

            print_sdk_message(message, phase)
            if isinstance(message, ResultMessage):
                result_msg = message
            elif isinstance(message, AssistantMessage):
                content = getattr(message, "message", None)
                if content:
                    for block in getattr(content, "content", []):
                        if hasattr(block, "text") and block.text:
                            last_text = block.text
    except Exception as e:
        if result_msg:
            elapsed = time.monotonic() - start
            if result_msg.is_error and result_msg.subtype == "error_max_budget_usd":
                print(f"{C.YELLOW}  [{phase}] Budget exceeded after {elapsed:.1f}s — using partial results{C.RESET}", flush=True)
            else:
                print(f"{C.DIM}  [{phase}] SDK cleanup exception (ignored, have result){C.RESET}", flush=True)
        else:
            elapsed = time.monotonic() - start
            print(f"\n{C.RED}[{phase}] Failed after {elapsed:.1f}s: {e}{C.RESET}", flush=True)
            raise

    if result_msg is None:
        raise RuntimeError(f"{phase} query returned no result message")
    return result_msg, last_text


async def review(
    diff: str, gates_summary: str, round_num: int,
    agent_prompt_path: Path, cwd: Path,
    max_turns: int = 10,
) -> tuple[list[Finding], float]:
    """Invoke reviewer agent. Returns (findings, cost_usd)."""
    agent_prompt = _load_agent_prompt(agent_prompt_path)
    prompt = _build_reviewer_prompt(diff, gates_summary, round_num, agent_prompt)

    options = ClaudeAgentOptions(
        permission_mode="dontAsk",
        cwd=cwd,
        max_turns=5,
        include_partial_messages=True,
    )

    result, last_text = await _run_query(prompt, options, "reviewer")

    # Parse findings from result text, or last assistant text as fallback
    findings: list[Finding] = []
    text_to_parse = result.result or last_text
    parsed = _extract_json(text_to_parse)
    if parsed:
        output = ReviewOutput.model_validate(parsed)
        findings = output.findings
    elif text_to_parse:
        print(f"{C.YELLOW}[reviewer] Could not parse JSON from response{C.RESET}", flush=True)
        print(f"{C.DIM}  First 300 chars: {text_to_parse[:300]}{C.RESET}", flush=True)

    cost = result.total_cost_usd or 0.0
    return findings, cost


async def fix(
    findings: list[Finding], round_num: int,
    agent_prompt_path: Path, cwd: Path,
    max_turns: int = 15,
) -> tuple[str, float]:
    """Invoke fixer agent. Returns (result_text, cost_usd)."""
    agent_prompt = _load_agent_prompt(agent_prompt_path)
    prompt = _build_fixer_prompt(findings, round_num, agent_prompt)

    options = ClaudeAgentOptions(
        permission_mode="acceptEdits",
        cwd=cwd,
        max_turns=max_turns,
        include_partial_messages=True,
    )

    result, last_text = await _run_query(prompt, options, "fixer")
    cost = result.total_cost_usd or 0.0
    return result.result or last_text or "", cost


def run_review_sync(**kwargs) -> tuple[list[Finding], float]:
    return asyncio.run(review(**kwargs))


def run_fix_sync(**kwargs) -> tuple[str, float]:
    return asyncio.run(fix(**kwargs))
