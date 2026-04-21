"""Round state management — persist to JSON files on disk."""

from __future__ import annotations

import json
from pathlib import Path

from .schema import (
    Finding, FixResult, GateResult, GroundResult,
    LoopState, RoundState,
)


class StateManager:
    def __init__(self, state_dir: Path, max_rounds: int = 3,
                 required_consecutive_clean: int = 1,
                 hard_fail_on_gate_failure_rounds: int = 3):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.loop_state = LoopState(
            max_rounds=max_rounds,
            required_consecutive_clean=required_consecutive_clean,
            hard_fail_on_gate_failure_rounds=hard_fail_on_gate_failure_rounds,
        )

    def record_review(self, round_num: int, gates: GateResult,
                      raw_findings: list[Finding], ground_result: GroundResult,
                      cost_usd: float = 0.0, duration_s: float = 0.0):
        """Record a review round's results."""
        round_state = RoundState(
            round_num=round_num,
            gates=gates,
            findings_raw=raw_findings,
            findings_grounded=ground_result.grounded,
            findings_dropped=ground_result.dropped,
            hallucination_rate=ground_result.hallucination_rate,
            cost_usd=cost_usd,
            duration_s=duration_s,
        )
        if round_num <= len(self.loop_state.rounds):
            self.loop_state.rounds[round_num - 1] = round_state
        else:
            self.loop_state.rounds.append(round_state)

        self._write_round_artifacts(round_num, raw_findings, ground_result)
        self._write_loop_state()

    def record_fix(self, round_num: int, fix_result: FixResult):
        """Attach fix result to a round."""
        if round_num <= len(self.loop_state.rounds):
            self.loop_state.rounds[round_num - 1].fix_result = fix_result
            self._write_loop_state()

    def record_regression(self, round_num: int):
        """Mark a round as having caused a regression."""
        if round_num <= len(self.loop_state.rounds):
            self.loop_state.rounds[round_num - 1].fix_reverted = True
            self._write_loop_state()

    def _write_round_artifacts(self, round_num: int,
                                raw_findings: list[Finding],
                                ground_result: GroundResult):
        raw_path = self.state_dir / f"findings_raw_round_{round_num}.json"
        raw_path.write_text(json.dumps(
            [f.model_dump() for f in raw_findings], indent=2
        ))

        grounded_path = self.state_dir / f"findings_grounded_round_{round_num}.json"
        grounded_path.write_text(json.dumps(
            ground_result.model_dump(), indent=2
        ))

    def _write_loop_state(self):
        path = self.state_dir / "pr-review-loop.json"
        path.write_text(self.loop_state.model_dump_json(indent=2))
