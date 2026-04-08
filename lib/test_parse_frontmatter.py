#!/usr/bin/env python3
"""Tests for parse_frontmatter.py"""
import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse_frontmatter.py")
passed = 0
failed = 0


def run_parser(content):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        try:
            return subprocess.run(
                [sys.executable, SCRIPT, f.name], capture_output=True, text=True
            )
        finally:
            os.unlink(f.name)


def check(name, condition):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}")
        failed += 1


def test_valid_full():
    result = run_parser(
        "---\n"
        "name: test-agent\n"
        "description: A test agent\n"
        "version: 1.0.0\n"
        "author: Test Author\n"
        "tags: [testing, demo]\n"
        "skills:\n"
        "  - slides\n"
        "  - code-review\n"
        "tools:\n"
        "  - python-pptx\n"
        "---\n\n"
        "Agent prompt body here.\n"
    )
    check("full frontmatter exits 0", result.returncode == 0)
    data = json.loads(result.stdout)
    check("name parsed", data["name"] == "test-agent")
    check("description parsed", data["description"] == "A test agent")
    check("version parsed", data["version"] == "1.0.0")
    check("author parsed", data["author"] == "Test Author")
    check("tags parsed", data["tags"] == ["testing", "demo"])
    check("skills parsed", data["skills"] == ["slides", "code-review"])
    check("tools parsed", data["tools"] == ["python-pptx"])


def test_minimal():
    result = run_parser(
        "---\n"
        "name: minimal\n"
        "description: Minimal agent\n"
        "version: 0.1.0\n"
        "author: Me\n"
        "---\n\n"
        "Body.\n"
    )
    check("minimal frontmatter exits 0", result.returncode == 0)
    data = json.loads(result.stdout)
    check("minimal name", data["name"] == "minimal")
    check("no skills field", "skills" not in data or data.get("skills") is None)


def test_missing_required():
    result = run_parser(
        "---\n" "name: incomplete\n" "description: Missing version and author\n" "---\n\n" "Body.\n"
    )
    check("missing fields exits non-zero", result.returncode != 0)
    check("error mentions version", "version" in result.stderr)
    check("error mentions author", "author" in result.stderr)


def test_no_frontmatter():
    result = run_parser("Just a regular markdown file.\n")
    check("no frontmatter exits non-zero", result.returncode != 0)
    check("error message present", "No frontmatter" in result.stderr)


def test_no_args():
    result = subprocess.run(
        [sys.executable, SCRIPT], capture_output=True, text=True
    )
    check("no args exits non-zero", result.returncode != 0)
    check("usage message", "Usage" in result.stderr)


if __name__ == "__main__":
    print("=== Frontmatter Parser Tests ===\n")
    test_valid_full()
    test_minimal()
    test_missing_required()
    test_no_frontmatter()
    test_no_args()
    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    sys.exit(0 if failed == 0 else 1)
