"""Tests for convergence.py — loop termination decisions."""

from engine.schema import (
    ConvergenceStatus, LoopState, RoundState, GateResult,
    Finding, FixResult, FixStatus, Severity, Category,
)
from engine.convergence import check


def _gates(all_pass: bool = True) -> GateResult:
    return GateResult(tests_pass=all_pass, lint_pass=all_pass, build_pass=all_pass, all_pass=all_pass)


def _finding(id: str = "F-001", severity: Severity = Severity.MUST_FIX) -> Finding:
    return Finding(
        id=id, severity=severity, category=Category.CORRECTNESS,
        claim="issue", file="a.js", line_start=1, line_end=1,
        quoted_code="x", suggested_fix="y",
    )


def _round(
    num: int, gates_pass: bool = True,
    must_fix_ids: list[str] | None = None,
    fix_result: FixResult | None = None,
) -> RoundState:
    findings = [_finding(id=fid) for fid in (must_fix_ids or [])]
    return RoundState(
        round_num=num, gates=_gates(gates_pass),
        findings_grounded=findings, fix_result=fix_result,
    )


class TestContinue:
    def test_empty_history(self):
        state = LoopState(max_rounds=3)
        assert check(state) == ConvergenceStatus.CONTINUE

    def test_has_must_fix_and_gates_pass(self):
        state = LoopState(max_rounds=3, rounds=[
            _round(1, gates_pass=True, must_fix_ids=["F-001"]),
        ])
        assert check(state) == ConvergenceStatus.CONTINUE


class TestPass:
    def test_one_clean_round(self):
        state = LoopState(max_rounds=3, required_consecutive_clean=1, rounds=[
            _round(1, gates_pass=True, must_fix_ids=[]),
        ])
        assert check(state) == ConvergenceStatus.PASS

    def test_two_consecutive_clean_rounds(self):
        state = LoopState(max_rounds=3, required_consecutive_clean=2, rounds=[
            _round(1, gates_pass=True, must_fix_ids=[]),
            _round(2, gates_pass=True, must_fix_ids=[]),
        ])
        assert check(state) == ConvergenceStatus.PASS

    def test_clean_findings_but_gates_fail_is_not_pass(self):
        state = LoopState(max_rounds=3, required_consecutive_clean=1, rounds=[
            _round(1, gates_pass=False, must_fix_ids=[]),
        ])
        assert check(state) != ConvergenceStatus.PASS


class TestStalled:
    def test_same_must_fix_two_rounds(self):
        state = LoopState(max_rounds=5, rounds=[
            _round(1, must_fix_ids=["F-001"]),
            _round(2, must_fix_ids=["F-001"]),
        ])
        assert check(state) == ConvergenceStatus.STALLED

    def test_different_must_fix_not_stalled(self):
        r1 = _round(1)
        r1.findings_grounded = [_finding(id="F-001")]
        r2 = _round(2)
        r2.findings_grounded = [Finding(
            id="F-002", severity=Severity.MUST_FIX, category=Category.SECURITY,
            claim="other", file="b.js", line_start=5, line_end=5,
            quoted_code="y", suggested_fix="z",
        )]
        state = LoopState(max_rounds=5, rounds=[r1, r2])
        assert check(state) == ConvergenceStatus.CONTINUE


class TestOscillating:
    def test_previously_fixed_finding_reappears(self):
        fix = FixResult(status=FixStatus.SUCCESS, fixed_finding_ids=["F-001"])
        state = LoopState(max_rounds=5, rounds=[
            _round(1, must_fix_ids=["F-001"], fix_result=fix),
            _round(2, must_fix_ids=[]),
            _round(3, must_fix_ids=["F-001"]),
        ])
        assert check(state) == ConvergenceStatus.OSCILLATING

    def test_new_finding_is_not_oscillating(self):
        fix = FixResult(status=FixStatus.SUCCESS, fixed_finding_ids=["F-001"])
        state = LoopState(max_rounds=5, rounds=[
            _round(1, must_fix_ids=["F-001"], fix_result=fix),
            _round(2, must_fix_ids=[]),
            _round(3, must_fix_ids=["F-099"]),
        ])
        assert check(state) != ConvergenceStatus.OSCILLATING


class TestGatesFail:
    def test_consecutive_gate_failures_no_findings(self):
        state = LoopState(max_rounds=10, hard_fail_on_gate_failure_rounds=3, rounds=[
            _round(1, gates_pass=False, must_fix_ids=[]),
            _round(2, gates_pass=False, must_fix_ids=[]),
            _round(3, gates_pass=False, must_fix_ids=[]),
        ])
        assert check(state) == ConvergenceStatus.GATES_FAIL

    def test_gate_failure_with_findings_continues(self):
        state = LoopState(max_rounds=10, hard_fail_on_gate_failure_rounds=3, rounds=[
            _round(1, gates_pass=False, must_fix_ids=["F-001"]),
            _round(2, gates_pass=False, must_fix_ids=["F-001"]),
            _round(3, gates_pass=False, must_fix_ids=["F-001"]),
        ])
        # Has findings, so it's STALLED not GATES_FAIL
        assert check(state) != ConvergenceStatus.GATES_FAIL


class TestMaxRounds:
    def test_hits_max_rounds(self):
        r1 = _round(1, must_fix_ids=["F-001"])
        r2 = _round(2)
        r2.findings_grounded = [Finding(
            id="F-002", severity=Severity.MUST_FIX, category=Category.SECURITY,
            claim="different", file="b.js", line_start=10, line_end=10,
            quoted_code="y", suggested_fix="z",
        )]
        state = LoopState(max_rounds=2, rounds=[r1, r2])
        assert check(state) == ConvergenceStatus.MAX_ROUNDS
