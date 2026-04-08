#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
passed=0
failed=0

pass() { echo "  PASS: $1"; ((passed++)) || true; }
fail() { echo "  FAIL: $1"; ((failed++)) || true; }

echo "=== Smoke Tests ==="

# --- Install ---
echo ""
echo "--- Install ---"
bash "$SCRIPT_DIR/install.sh" slides >/dev/null 2>&1

# Check commands symlink exists and points to correct target
cmd_link="$CLAUDE_DIR/commands/slides"
if [[ -L "$cmd_link" ]]; then
  actual="$(readlink "$cmd_link")"
  if [[ "$actual" == "$SCRIPT_DIR/slides/commands" ]]; then
    pass "commands symlink points to registry"
  else
    fail "commands symlink points to $actual (expected $SCRIPT_DIR/slides/commands)"
  fi
else
  fail "commands symlink not created at $cmd_link"
fi

# Check generate.md is accessible through symlink
if [[ -f "$cmd_link/generate.md" ]]; then
  pass "generate.md accessible through symlink"
else
  fail "generate.md not accessible through symlink"
fi

# --- Status ---
echo ""
echo "--- Status ---"
status_out="$(bash "$SCRIPT_DIR/install.sh" --status 2>&1)"
if echo "$status_out" | grep -q "slides"; then
  pass "--status lists slides package"
else
  fail "--status does not list slides package"
fi

# --- Name validation ---
echo ""
echo "--- Name Validation ---"
out="$(bash "$SCRIPT_DIR/install.sh" "../traversal" 2>&1 || true)"
if echo "$out" | grep -q "Invalid package name"; then
  pass "rejects path traversal in name"
else
  fail "does not reject path traversal in name"
fi

out="$(bash "$SCRIPT_DIR/install.sh" ".hidden" 2>&1 || true)"
if echo "$out" | grep -q "Invalid package name"; then
  pass "rejects hidden directory name"
else
  fail "does not reject hidden directory name"
fi

# --- Single-package uninstall ---
echo ""
echo "--- Single-package Uninstall ---"
bash "$SCRIPT_DIR/install.sh" --uninstall slides >/dev/null 2>&1

if [[ ! -L "$cmd_link" ]]; then
  pass "commands symlink removed after --uninstall slides"
else
  fail "commands symlink still exists after --uninstall slides"
fi

# Status should show missing after uninstall
status_out="$(bash "$SCRIPT_DIR/install.sh" --status 2>&1)"
if echo "$status_out" | grep -q "missing"; then
  pass "--status shows missing after uninstall"
else
  fail "--status does not show missing after uninstall"
fi

# --- Re-install for full uninstall test ---
echo ""
echo "--- Full Uninstall ---"
bash "$SCRIPT_DIR/install.sh" slides >/dev/null 2>&1
bash "$SCRIPT_DIR/install.sh" --uninstall >/dev/null 2>&1

if [[ ! -L "$cmd_link" ]]; then
  pass "commands symlink removed after --uninstall (all)"
else
  fail "commands symlink still exists after --uninstall (all)"
fi

# --- Re-install to leave in good state ---
bash "$SCRIPT_DIR/install.sh" slides >/dev/null 2>&1

# --- Summary ---
echo ""
echo "=== Results: $passed passed, $failed failed ==="
[[ $failed -eq 0 ]] && exit 0 || exit 1
