"""Real-time streaming display for agent execution."""

from __future__ import annotations

import sys
import time


class Colors:
    RESET = "\x1b[0m"
    DIM = "\x1b[2m"
    BOLD = "\x1b[1m"
    CYAN = "\x1b[36m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"
    MAGENTA = "\x1b[35m"


C = Colors


def print_phase(name: str):
    print(f"\n{C.BOLD}--- {name} ---{C.RESET}\n")


def print_info(phase: str, msg: str):
    print(f"{C.CYAN}[{phase}]{C.RESET} {msg}")


def print_success(phase: str, msg: str):
    print(f"{C.GREEN}[{phase}]{C.RESET} {msg}")


def print_warn(phase: str, msg: str):
    print(f"{C.YELLOW}[{phase}]{C.RESET} {msg}")


def print_error(phase: str, msg: str):
    print(f"{C.RED}[{phase}]{C.RESET} {msg}")


def print_finding(finding, indent: str = "  "):
    sev = finding.severity.value
    color = C.RED if sev == "must-fix" else C.DIM
    print(f"{indent}{color}[{sev}]{C.RESET} {finding.id}: {finding.claim} ({finding.file}:{finding.line_start})")


def print_ground_result(grounded: list, dropped: list, duration_s: float):
    total = len(grounded) + len(dropped)
    rate = (len(dropped) / total * 100) if total else 0
    print_info("ground", f"{len(grounded)} grounded, {len(dropped)} dropped ({rate:.0f}% hallucination) {C.DIM}({duration_s:.1f}s){C.RESET}")
    for f in grounded:
        print(f"  {C.GREEN}✓{C.RESET} {f.id}: {f.claim}")
    for d in dropped:
        print(f"  {C.RED}✗{C.RESET} {d.get('id', '?')}: {d.get('grounding_error', '?')}")


def print_gate_result(gates, phase: str = "gates"):
    status = f"tests={'✓' if gates.tests_pass else '✗'} lint={'✓' if gates.lint_pass else '✗'} build={'✓' if gates.build_pass else '✗'}"
    fn = print_success if gates.all_pass else print_error
    fn(phase, status)


def print_sdk_message(message, phase: str):
    """Handle Claude Agent SDK streaming message types (Python SDK uses classes, not string types)."""
    from claude_agent_sdk import StreamEvent, AssistantMessage, ResultMessage, SystemMessage

    prefix = f"{C.CYAN}[{phase}]{C.RESET}"

    if isinstance(message, StreamEvent):
        event = message.event
        if isinstance(event, dict) and event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                sys.stdout.write(f"{C.DIM}{delta.get('text', '')}{C.RESET}")
                sys.stdout.flush()

    elif isinstance(message, AssistantMessage):
        msg_content = getattr(message, "message", None)
        if msg_content:
            content = getattr(msg_content, "content", None) or []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        name = block.get("name", "?")
                        inp = str(block.get("input", ""))[:100]
                        print(f"\n{prefix} {C.MAGENTA}tool:{C.RESET} {name}({inp})", flush=True)
                elif getattr(block, "type", None) == "tool_use":
                    name = getattr(block, "name", "?")
                    inp = str(getattr(block, "input", ""))[:100]
                    print(f"\n{prefix} {C.MAGENTA}tool:{C.RESET} {name}({inp})", flush=True)

    elif isinstance(message, ResultMessage):
        cost = message.total_cost_usd
        turns = message.num_turns
        cost_str = f"${cost:.4f}" if cost else "?"
        print(f"\n{prefix} {C.GREEN}Done{C.RESET} (cost: {cost_str}, turns: {turns or '?'})", flush=True)

    elif isinstance(message, SystemMessage):
        subtype = getattr(message, "subtype", None)
        if subtype == "notification":
            text = getattr(message, "text", "")
            if text:
                print(f"{prefix} {C.YELLOW}{text}{C.RESET}", flush=True)


class Timer:
    def __init__(self):
        self._start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def reset(self) -> float:
        elapsed = self.elapsed()
        self._start = time.monotonic()
        return elapsed
