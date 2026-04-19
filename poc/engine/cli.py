"""CLI entry point for the review-fix engine."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config import Config
from .orchestrator import run
from .progress import C, print_info, print_success, print_error
from .schema import ConvergenceStatus


def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="SDK-based PR review-fix loop engine",
    )
    parser.add_argument("--pr", type=int, help="PR number to review")
    parser.add_argument("--repo", type=str, help="GitHub repo (owner/repo)")
    parser.add_argument("--diff-file", type=Path, help="Path to diff file")
    parser.add_argument("--dry-run", action="store_true", help="Reviewer only, skip fixer")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--budget", type=float, default=5.0, help="Total budget in USD")
    parser.add_argument("--budget-per-agent", type=float, default=0.50)
    parser.add_argument("--test-cmd", type=str, default="npm test")
    parser.add_argument("--lint-cmd", type=str, default="")
    parser.add_argument("--build-cmd", type=str, default="")
    parser.add_argument("--cwd", type=Path, default=None, help="Override working directory (default: git repo root)")

    args = parser.parse_args()
    config = Config(
        pr_number=args.pr,
        repo=args.repo,
        diff_file=args.diff_file,
        dry_run=args.dry_run,
        max_rounds=args.max_rounds,
        budget_total=args.budget,
        budget_per_agent=args.budget_per_agent,
        test_cmd=args.test_cmd,
        lint_cmd=args.lint_cmd,
        build_cmd=args.build_cmd,
    )
    if args.cwd:
        config.cwd = args.cwd
    return config


def print_summary(result):
    state = result.state
    status = result.status

    print(f"\n{C.BOLD}=== Summary ==={C.RESET}")
    print_info("result", f"Status: {status.value}")
    print_info("result", f"Rounds: {len(state.rounds)}/{state.max_rounds}")
    print_info("result", f"Cost: ${result.total_cost_usd:.4f}")
    print_info("result", f"Duration: {result.total_duration_s:.1f}s")

    if state.rounds:
        rates = [r.hallucination_rate for r in state.rounds]
        print_info("result", f"Hallucination rates: {[f'{r:.0%}' for r in rates]}")

    for r in state.rounds:
        must_fix = [f for f in r.findings_grounded if f.severity.value == "must-fix"]
        nice = [f for f in r.findings_grounded if f.severity.value == "nice-to-have"]
        print_info(f"round {r.round_num}", f"must-fix={len(must_fix)} nice-to-have={len(nice)} halluc={r.hallucination_rate:.0%}")

    if status == ConvergenceStatus.PASS:
        print_success("result", "PR review complete — all clean!")
    elif status in (ConvergenceStatus.STALLED, ConvergenceStatus.OSCILLATING):
        print_error("result", "Loop did not converge — human review needed")
    elif status == ConvergenceStatus.REGRESSION:
        print_error("result", "Fixer introduced regressions — changes reverted")
    elif status == ConvergenceStatus.MAX_ROUNDS:
        print_error("result", f"Hit max rounds ({state.max_rounds}) — remaining findings need human review")


def main():
    config = parse_args()

    try:
        result = asyncio.run(run(config))
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Interrupted.{C.RESET}")
        sys.exit(130)
    except Exception as e:
        print_error("fatal", str(e))
        sys.exit(1)

    print_summary(result)

    if result.status != ConvergenceStatus.PASS:
        sys.exit(1)


if __name__ == "__main__":
    main()
