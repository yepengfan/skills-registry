"""Decide whether the review-fix loop should continue or terminate."""

from __future__ import annotations

from .schema import ConvergenceStatus, LoopState, RoundState, Severity


def _finding_key(f) -> tuple:
    return (f.file, f.line_start, f.category)


def _must_fix_set(round_state: RoundState) -> set[tuple]:
    return {
        _finding_key(f)
        for f in round_state.findings_grounded
        if f.severity == Severity.MUST_FIX
    }


def _must_fix_ids(round_state: RoundState) -> set[str]:
    return {
        f.id
        for f in round_state.findings_grounded
        if f.severity == Severity.MUST_FIX
    }


def check(state: LoopState) -> ConvergenceStatus:
    """Check loop convergence. Returns a ConvergenceStatus."""
    history = state.rounds
    if not history:
        return ConvergenceStatus.CONTINUE

    current = history[-1]
    current_must_fix = _must_fix_set(current)

    # PASS: last N rounds all clean (zero must-fix + all gates pass)
    n = state.required_consecutive_clean
    if len(history) >= n:
        recent = history[-n:]
        all_clean = all(
            not _must_fix_set(r) and r.gates.all_pass
            for r in recent
        )
        if all_clean:
            return ConvergenceStatus.PASS

    # STALLED: last 2 rounds have identical non-empty must-fix set
    if len(history) >= 2 and current_must_fix:
        prev_must_fix = _must_fix_set(history[-2])
        if current_must_fix == prev_must_fix:
            return ConvergenceStatus.STALLED

    # OSCILLATING: current round has findings that were fixed in a previous round
    if len(history) >= 3:
        current_ids = _must_fix_ids(current)
        for prev_round in history[:-1]:
            if prev_round.fix_result and prev_round.fix_result.fixed_finding_ids:
                fixed_ids = set(prev_round.fix_result.fixed_finding_ids)
                if current_ids & fixed_ids:
                    return ConvergenceStatus.OSCILLATING

    # FAIL_GATES: N consecutive rounds with gates failing but no must-fix findings
    cap = state.hard_fail_on_gate_failure_rounds
    if len(history) >= cap:
        recent = history[-cap:]
        stuck = all(
            not r.gates.all_pass and not _must_fix_set(r)
            for r in recent
        )
        if stuck:
            return ConvergenceStatus.GATES_FAIL

    # MAX_ROUNDS
    if len(history) >= state.max_rounds:
        return ConvergenceStatus.MAX_ROUNDS

    return ConvergenceStatus.CONTINUE
