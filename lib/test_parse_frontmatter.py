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


def run_parser(content, extra_args=None):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        try:
            cmd = [sys.executable, SCRIPT]
            if extra_args:
                cmd.extend(extra_args)
            cmd.append(f.name)
            return subprocess.run(cmd, capture_output=True, text=True)
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


def test_body_extraction():
    content = (
        "---\n"
        "name: test\n"
        "description: Test\n"
        "version: 1.0.0\n"
        "author: Me\n"
        "---\n\n"
        "Body content here.\n"
        "Second line.\n"
    )
    result = run_parser(content, ["--body"])
    check("--body exits 0", result.returncode == 0)
    check("--body returns body", "Body content here." in result.stdout)
    check("--body strips frontmatter", "name: test" not in result.stdout)
    check("--body strips delimiters", "---" not in result.stdout)


def test_empty_inline_list():
    result = run_parser(
        "---\n"
        "name: empty-list\n"
        "description: Agent with empty tags\n"
        "version: 1.0.0\n"
        "author: Me\n"
        "tags: []\n"
        "---\n\n"
        "Body.\n"
    )
    check("empty list exits 0", result.returncode == 0)
    data = json.loads(result.stdout)
    check("empty list parsed as list", isinstance(data.get("tags"), list))
    check("empty list is empty", data.get("tags") == [])


if __name__ == "__main__":
    print("=== Frontmatter Parser Tests ===\n")
    test_valid_full()
    test_minimal()
    test_missing_required()
    test_no_frontmatter()
    test_no_args()
    test_body_extraction()
    test_empty_inline_list()
    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    sys.exit(0 if failed == 0 else 1)
