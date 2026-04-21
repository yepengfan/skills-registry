"""Tests for grounding.py — verifying findings against real files."""

import tempfile
from pathlib import Path

from engine.schema import Finding, Severity, Category
from engine.grounding import verify, _normalize


def _make_finding(**overrides) -> Finding:
    defaults = dict(
        id="F-001", severity=Severity.MUST_FIX, category=Category.CORRECTNESS,
        claim="test issue", file="src/foo.js", line_start=1, line_end=1,
        quoted_code="const x = 1", suggested_fix="fix it",
    )
    defaults.update(overrides)
    return Finding(**defaults)


def _make_repo(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp())
    for name, content in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp


class TestNormalize:
    def test_strips_whitespace(self):
        assert _normalize("  hello  world  ") == "hello world"

    def test_collapses_internal(self):
        assert _normalize("a   b\n  c   d") == "a b\nc d"

    def test_multiline(self):
        assert _normalize("  line1  \n  line2  ") == "line1\nline2"


class TestGrounding:
    def test_exact_match(self):
        repo = _make_repo({"src/foo.js": "const x = 1\nconst y = 2\n"})
        findings = [_make_finding(file="src/foo.js", line_start=1, line_end=1, quoted_code="const x = 1")]
        result = verify(findings, repo)
        assert result.grounded_count == 1
        assert result.dropped_count == 0
        assert result.hallucination_rate == 0.0

    def test_whitespace_normalized_match(self):
        repo = _make_repo({"src/foo.js": "const   x  =   1\n"})
        findings = [_make_finding(file="src/foo.js", line_start=1, line_end=1, quoted_code="const x = 1")]
        result = verify(findings, repo)
        assert result.grounded_count == 1

    def test_multiline_match(self):
        repo = _make_repo({"src/foo.js": "line1\nline2\nline3\nline4\n"})
        findings = [_make_finding(file="src/foo.js", line_start=2, line_end=3, quoted_code="line2\nline3")]
        result = verify(findings, repo)
        assert result.grounded_count == 1

    def test_file_not_found(self):
        repo = _make_repo({})
        findings = [_make_finding(file="src/missing.js")]
        result = verify(findings, repo)
        assert result.dropped_count == 1
        assert "file not found" in result.dropped[0]["grounding_error"]

    def test_line_out_of_bounds(self):
        repo = _make_repo({"src/foo.js": "one line\n"})
        findings = [_make_finding(file="src/foo.js", line_start=5, line_end=5, quoted_code="nope")]
        result = verify(findings, repo)
        assert result.dropped_count == 1
        assert "out of bounds" in result.dropped[0]["grounding_error"]

    def test_quoted_code_mismatch(self):
        repo = _make_repo({"src/foo.js": "const x = 1\n"})
        findings = [_make_finding(file="src/foo.js", line_start=1, line_end=1, quoted_code="const y = 2")]
        result = verify(findings, repo)
        assert result.dropped_count == 1
        assert "does not match" in result.dropped[0]["grounding_error"]

    def test_path_traversal_blocked(self):
        repo = _make_repo({"src/foo.js": "ok\n"})
        findings = [_make_finding(file="../../../etc/passwd", line_start=1, line_end=1, quoted_code="root")]
        result = verify(findings, repo)
        assert result.dropped_count == 1
        assert "escapes repo" in result.dropped[0]["grounding_error"]

    def test_sliding_window_finds_shifted_code(self):
        lines = ["header\n"] + [f"line{i}\n" for i in range(1, 20)]
        repo = _make_repo({"src/foo.js": "".join(lines)})
        # Finding says line 5 but code is actually at line 8
        findings = [_make_finding(file="src/foo.js", line_start=5, line_end=5, quoted_code="line7")]
        result = verify(findings, repo, sliding_window=10)
        assert result.grounded_count == 1

    def test_sliding_window_no_match_beyond_range(self):
        lines = [f"line{i}\n" for i in range(1, 30)]
        repo = _make_repo({"src/foo.js": "".join(lines)})
        # Finding says line 1 but code is at line 25 — beyond window of 10
        findings = [_make_finding(file="src/foo.js", line_start=1, line_end=1, quoted_code="line25")]
        result = verify(findings, repo, sliding_window=10)
        assert result.dropped_count == 1

    def test_hallucination_rate_calculation(self):
        repo = _make_repo({"a.js": "real\n", "b.js": "also real\n"})
        findings = [
            _make_finding(id="F-001", file="a.js", line_start=1, line_end=1, quoted_code="real"),
            _make_finding(id="F-002", file="a.js", line_start=1, line_end=1, quoted_code="fake"),
            _make_finding(id="F-003", file="b.js", line_start=1, line_end=1, quoted_code="also real"),
            _make_finding(id="F-004", file="c.js", line_start=1, line_end=1, quoted_code="missing"),
        ]
        result = verify(findings, repo)
        assert result.grounded_count == 2
        assert result.dropped_count == 2
        assert result.hallucination_rate == 0.5

    def test_empty_findings(self):
        repo = _make_repo({})
        result = verify([], repo)
        assert result.grounded_count == 0
        assert result.dropped_count == 0
        assert result.hallucination_rate == 0.0
