"""Run deterministic test/lint/build gates."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .schema import GateResult


def _run_cmd(cmd: str, cwd: Path) -> tuple[bool, str]:
    """Run a shell command, return (passed, tail of output)."""
    if not cmd:
        return True, ""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=300,
        )
        output = (result.stdout + result.stderr)[-2048:]
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "command timed out after 300s"
    except Exception as e:
        return False, str(e)


def run(cwd: Path, test_cmd: str = "npm test", lint_cmd: str = "", build_cmd: str = "") -> GateResult:
    """Run all gates and return structured results."""
    tests_pass, test_output = _run_cmd(test_cmd, cwd)
    lint_pass, lint_output = _run_cmd(lint_cmd, cwd)
    build_pass, build_output = _run_cmd(build_cmd, cwd)

    return GateResult(
        tests_pass=tests_pass,
        lint_pass=lint_pass,
        build_pass=build_pass,
        all_pass=tests_pass and lint_pass and build_pass,
        test_output=test_output,
        lint_output=lint_output,
        build_output=build_output,
    )


def gates_regressed(before: GateResult, after: GateResult) -> bool:
    """Check if any gate that was passing now fails."""
    if before.tests_pass and not after.tests_pass:
        return True
    if before.lint_pass and not after.lint_pass:
        return True
    if before.build_pass and not after.build_pass:
        return True
    return False
