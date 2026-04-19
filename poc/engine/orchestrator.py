"""Main review-fix loop — deterministic code orchestration (Principle #1)."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from . import agents, grounding, gates
from .convergence import check
from .config import Config
from .progress import (
    print_phase, print_info, print_warn, print_error, print_success,
    print_finding, print_ground_result, print_gate_result, Timer, C,
)
from .schema import ConvergenceStatus, LoopResult, Severity
from .state import StateManager


def _get_diff(config: Config) -> str:
    if config.diff_file:
        return config.diff_file.read_text()
    if config.pr_number:
        repo_flag = f"--repo {config.repo}" if config.repo else ""
        return subprocess.run(
            f"gh pr diff {config.pr_number} {repo_flag}",
            shell=True, capture_output=True, text=True, cwd=config.cwd,
        ).stdout
    return SAMPLE_DIFF


def _checkout_pr_branch(config: Config) -> str | None:
    """Checkout the PR branch so files exist for grounding. Returns branch name or None."""
    if not config.pr_number:
        return None
    repo_flag = f"--repo {config.repo}" if config.repo else ""

    # Get PR branch name
    result = subprocess.run(
        f"gh pr view {config.pr_number} {repo_flag} --json headRefName -q .headRefName",
        shell=True, capture_output=True, text=True, cwd=config.cwd,
    )
    branch = result.stdout.strip()
    if not branch:
        return None

    # Check if we're already on it
    current = subprocess.run(
        "git branch --show-current",
        shell=True, capture_output=True, text=True, cwd=config.cwd,
    ).stdout.strip()
    if current == branch:
        return branch

    # Try to checkout
    checkout = subprocess.run(
        f"gh pr checkout {config.pr_number} {repo_flag}",
        shell=True, capture_output=True, text=True, cwd=config.cwd,
    )
    if checkout.returncode == 0:
        return branch
    return None


def _gates_summary(gate_result) -> str:
    return (
        f"- tests_pass: {str(gate_result.tests_pass).lower()}\n"
        f"- lint_pass: {str(gate_result.lint_pass).lower()}\n"
        f"- build_pass: {str(gate_result.build_pass).lower()}"
    )


def _commit_fixes(cwd: Path, round_num: int, findings: list):
    """Orchestrator commits after gates pass (Principle #9)."""
    ids = ", ".join(f.id for f in findings)
    msg = f"fix(pr-review): address round {round_num} findings\n\n{ids}"
    subprocess.run("git add -A", shell=True, cwd=cwd, capture_output=True)
    subprocess.run(
        f'git commit -m "{msg}"',
        shell=True, cwd=cwd, capture_output=True,
    )


def _revert_changes(cwd: Path):
    subprocess.run("git checkout -- .", shell=True, cwd=cwd, capture_output=True)
    subprocess.run("git clean -fd", shell=True, cwd=cwd, capture_output=True)


async def run(config: Config) -> LoopResult:
    """Execute the review-fix loop."""
    total_timer = Timer()
    state_dir = config.cwd / config.state_dir
    state = StateManager(
        state_dir, config.max_rounds,
        config.required_consecutive_clean,
        config.hard_fail_on_gate_failure_rounds,
    )

    reviewer_path = Path(__file__).parent.parent / "agents" / "reviewer.md"
    fixer_path = Path(__file__).parent.parent / "agents" / "fixer.md"

    print(f"{C.BOLD}=== Review-Fix Engine ==={C.RESET}")
    print_info("setup", f"max_rounds={config.max_rounds} cwd={config.cwd}")

    # Auto-checkout PR branch so files exist for grounding
    if config.pr_number:
        print_info("setup", f"Checking out PR #{config.pr_number} branch...")
        branch = _checkout_pr_branch(config)
        if branch:
            print_success("setup", f"On branch: {branch}")
        else:
            print_warn("setup", "Could not checkout PR branch — grounding may fail")

    diff = _get_diff(config)
    print_info("setup", f"Diff: {len(diff)} chars, {diff.count(chr(10))} lines")

    # Initial gates
    print_phase("Initial Gates")
    initial_gates = gates.run(config.cwd, config.test_cmd, config.lint_cmd, config.build_cmd)
    print_gate_result(initial_gates)

    total_cost = 0.0

    for round_num in range(1, config.max_rounds + 1):
        round_timer = Timer()
        print_phase(f"Round {round_num}/{config.max_rounds}")

        # Phase 1: Gates
        if round_num > 1:
            gate_result = gates.run(config.cwd, config.test_cmd, config.lint_cmd, config.build_cmd)
            print_gate_result(gate_result, f"round {round_num} gates")
        else:
            gate_result = initial_gates

        # Phase 2: Review (Principle #3: embed diff in prompt)
        print_info("review", "Invoking reviewer agent...")
        findings, review_cost = await agents.review(
            diff=diff,
            gates_summary=_gates_summary(gate_result),
            round_num=round_num,
            agent_prompt_path=reviewer_path,
            cwd=config.cwd,
            max_turns=config.reviewer_max_turns,
        )
        total_cost += review_cost

        print_info("review", f"Found {len(findings)} issues (${review_cost:.4f})")
        for f in findings:
            print_finding(f)

        # Phase 3: Ground (Principle #2: verify claims)
        ground_timer = Timer()
        ground_result = grounding.verify(findings, config.cwd)
        ground_duration = ground_timer.elapsed()
        print_ground_result(ground_result.grounded, ground_result.dropped, ground_duration)

        # Record round state
        state.record_review(
            round_num, gate_result, findings, ground_result,
            cost_usd=review_cost, duration_s=round_timer.elapsed(),
        )

        # Phase 4: Convergence check
        status = check(state.loop_state)
        if status != ConvergenceStatus.CONTINUE:
            print_info("convergence", f"{status.value}")
            return LoopResult(
                status=status, state=state.loop_state,
                total_cost_usd=total_cost, total_duration_s=total_timer.elapsed(),
            )

        # Phase 5: Fix
        must_fix = [f for f in ground_result.grounded if f.severity == Severity.MUST_FIX]
        if not must_fix:
            print_warn("fix", "No must-fix findings to fix, continuing to next round")
            continue

        if config.dry_run:
            print_warn("dry-run", f"Would fix {len(must_fix)} findings. Skipping.")
            continue

        print_info("fix", f"Invoking fixer agent on {len(must_fix)} findings...")
        fix_text, fix_cost = await agents.fix(
            findings=must_fix,
            round_num=round_num,
            agent_prompt_path=fixer_path,
            cwd=config.cwd,
            max_turns=config.fixer_max_turns,
        )
        total_cost += fix_cost
        print_info("fix", f"Fixer done (${fix_cost:.4f})")

        # Phase 6: Verify (Principle #9: orchestrator commits after gates pass)
        post_fix_gates = gates.run(config.cwd, config.test_cmd, config.lint_cmd, config.build_cmd)
        print_gate_result(post_fix_gates, "post-fix gates")

        if gates.gates_regressed(initial_gates, post_fix_gates):
            print_error("regression", "Gates regressed after fix — reverting")
            _revert_changes(config.cwd)
            state.record_regression(round_num)
            return LoopResult(
                status=ConvergenceStatus.REGRESSION, state=state.loop_state,
                total_cost_usd=total_cost, total_duration_s=total_timer.elapsed(),
            )

        _commit_fixes(config.cwd, round_num, must_fix)
        print_success("commit", f"Round {round_num} fixes committed")

    return LoopResult(
        status=ConvergenceStatus.MAX_ROUNDS, state=state.loop_state,
        total_cost_usd=total_cost, total_duration_s=total_timer.elapsed(),
    )


SAMPLE_DIFF = """diff --git a/lib/example.js b/lib/example.js
index 1234567..abcdefg 100644
--- a/lib/example.js
+++ b/lib/example.js
@@ -10,6 +10,15 @@ function validateInput(input) {
   return true
 }

+function processUserData(data) {
+  const query = "SELECT * FROM users WHERE id = " + data.userId
+  const result = db.execute(query)
+  if (result == null) {
+    return { error: "not found" }
+  }
+  return { user: result, token: Math.random().toString(36) }
+}
+
 module.exports = { validateInput }
"""
