from dataclasses import dataclass, field
from pathlib import Path
import subprocess


def _git_root() -> Path:
    """Auto-detect git repo root, fall back to cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return Path.cwd()


@dataclass
class Config:
    cwd: Path = field(default_factory=_git_root)
    pr_number: int | None = None
    repo: str | None = None
    diff_file: Path | None = None
    dry_run: bool = False

    max_rounds: int = 3
    required_consecutive_clean: int = 1
    hard_fail_on_gate_failure_rounds: int = 3

    budget_per_agent: float = 2.00
    budget_total: float = 10.00
    reviewer_max_turns: int = 30
    fixer_max_turns: int = 30

    state_dir: str = ".pr-review-state"

    test_cmd: str = "npm test"
    lint_cmd: str = ""
    build_cmd: str = ""
