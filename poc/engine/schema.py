from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    MUST_FIX = "must-fix"
    NICE_TO_HAVE = "nice-to-have"


class Category(str, Enum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    STYLE = "style"
    TESTING = "testing"
    OTHER = "other"


class Finding(BaseModel):
    id: str = Field(description="Unique ID like F-001, F-002")
    severity: Severity
    category: Category
    claim: str = Field(description="One-sentence description of the issue")
    reasoning: str = Field(default="", description="Why this is a problem")
    file: str = Field(description="File path relative to repo root")
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    quoted_code: str = Field(description="Verbatim copy of lines from the file")
    suggested_fix: str = Field(description="Concrete fix description or code")


class ReviewOutput(BaseModel):
    summary: str = Field(default="", description="One-sentence overall assessment")
    findings: list[Finding] = Field(default_factory=list)


class GateResult(BaseModel):
    tests_pass: bool = False
    lint_pass: bool = True
    build_pass: bool = True
    all_pass: bool = False
    test_output: str = ""
    lint_output: str = ""
    build_output: str = ""


class FixStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class FixResult(BaseModel):
    status: FixStatus = FixStatus.FAILED
    commit_sha: str = ""
    fixed_finding_ids: list[str] = Field(default_factory=list)
    skipped_finding_ids: list[str] = Field(default_factory=list)
    skip_reasons: dict[str, str] = Field(default_factory=dict)


class GroundResult(BaseModel):
    grounded: list[Finding] = Field(default_factory=list)
    dropped: list[dict] = Field(default_factory=list)
    raw_count: int = 0
    grounded_count: int = 0
    dropped_count: int = 0
    hallucination_rate: float = 0.0


class ConvergenceStatus(str, Enum):
    CONTINUE = "CONTINUE"
    PASS = "PASS"
    STALLED = "FAIL_STALLED"
    GATES_FAIL = "FAIL_GATES"
    OSCILLATING = "FAIL_OSCILLATING"
    REGRESSION = "FAIL_REGRESSION"
    MAX_ROUNDS = "MAX_ROUNDS"


class RoundState(BaseModel):
    round_num: int
    gates: GateResult
    findings_raw: list[Finding] = Field(default_factory=list)
    findings_grounded: list[Finding] = Field(default_factory=list)
    findings_dropped: list[dict] = Field(default_factory=list)
    hallucination_rate: float = 0.0
    fix_result: FixResult | None = None
    fix_reverted: bool = False
    cost_usd: float = 0.0
    duration_s: float = 0.0


class LoopState(BaseModel):
    max_rounds: int = 3
    required_consecutive_clean: int = 1
    hard_fail_on_gate_failure_rounds: int = 3
    rounds: list[RoundState] = Field(default_factory=list)


class LoopResult(BaseModel):
    status: ConvergenceStatus
    state: LoopState
    total_cost_usd: float = 0.0
    total_duration_s: float = 0.0


def findings_json_schema() -> dict:
    """Generate JSON Schema for SDK outputFormat from ReviewOutput model."""
    return ReviewOutput.model_json_schema()
