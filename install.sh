#!/usr/bin/env bash
set -euo pipefail

REGISTRY_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

# Colors
green='\033[0;32m'
yellow='\033[0;33m'
red='\033[0;31m'
reset='\033[0m'

usage() {
  echo "Usage: $0 [--uninstall [name] | --status | <skill-name>]"
  echo ""
  echo "  (no args)            Install all skill packages"
  echo "  <skill-name>         Install a single skill package"
  echo "  --uninstall          Remove all symlinks managed by this registry"
  echo "  --uninstall <name>   Remove symlinks for a single package"
  echo "  --status             Show installed status of each skill"
  exit 1
}

# Validate package name: only allow alphanumeric, hyphens, and underscores
validate_name() {
  local name="$1"
  if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo -e "${red}Invalid package name: $name${reset}"
    return 1
  fi
}

# Resolve a symlink to its absolute target path
resolve_link() {
  local link="$1"
  if command -v realpath &>/dev/null; then
    realpath "$link" 2>/dev/null || readlink "$link"
  else
    readlink "$link"
  fi
}

# Find all skill packages (directories with commands/ or skills/ subdirs)
list_packages() {
  local _old_nullglob
  _old_nullglob=$(shopt -p nullglob 2>/dev/null || true)
  shopt -s nullglob
  for dir in "$REGISTRY_DIR"/*/; do
    local name
    name="$(basename "$dir")"
    # Skip hidden directories
    [[ "$name" == .* ]] && continue
    # A valid package has at least one of: commands/, skills/
    if [[ -d "$dir/commands" || -d "$dir/skills" ]]; then
      echo "$name"
    fi
  done | sort
  eval "$_old_nullglob" 2>/dev/null || true
}

install_package() {
  local name="$1"
  validate_name "$name" || return 1
  local pkg_dir="$REGISTRY_DIR/$name"
  local installed=0

  if [[ ! -d "$pkg_dir" ]]; then
    echo -e "${red}Package not found: $name${reset}"
    return 1
  fi

  # Install commands: symlink commands/ → ~/.claude/commands/<name>/
  if [[ -d "$pkg_dir/commands" ]]; then
    local cmd_dst="$CLAUDE_DIR/commands/$name"
    mkdir -p "$CLAUDE_DIR/commands"

    if [[ -L "$cmd_dst" ]]; then
      rm "$cmd_dst"
    elif [[ -d "$cmd_dst" ]]; then
      echo -e "${yellow}Warning: $cmd_dst exists and is not a symlink, skipping${reset}"
      return 1
    fi

    ln -s "$pkg_dir/commands" "$cmd_dst"
    echo -e "${green}  commands -> $cmd_dst${reset}"
    installed=1
  fi

  # Install context skills: symlink each skills/*.md → ~/.claude/skills/
  if [[ -d "$pkg_dir/skills" ]]; then
    mkdir -p "$CLAUDE_DIR/skills"

    for skill_file in "$pkg_dir/skills"/*.md; do
      [[ -f "$skill_file" ]] || continue
      local fname
      fname="$(basename "$skill_file")"
      local skill_dst="$CLAUDE_DIR/skills/$fname"

      if [[ -L "$skill_dst" ]]; then
        rm "$skill_dst"
      elif [[ -f "$skill_dst" ]]; then
        echo -e "${yellow}Warning: $skill_dst exists and is not a symlink, skipping${reset}"
        continue
      fi

      ln -s "$skill_file" "$skill_dst"
      echo -e "${green}  skill $fname -> $skill_dst${reset}"
      installed=1
    done
  fi

  if [[ $installed -eq 1 ]]; then
    echo -e "${green}Installed: $name${reset}"
  else
    echo -e "${yellow}Package $name has no commands/ or skills/ to install${reset}"
  fi
}

uninstall_package() {
  local name="$1"
  validate_name "$name" || return 1
  local pkg_dir="$REGISTRY_DIR/$name"

  # Remove commands symlink (only if it points back to this registry)
  local cmd_dst="$CLAUDE_DIR/commands/$name"
  if [[ -L "$cmd_dst" ]]; then
    local actual
    actual="$(resolve_link "$cmd_dst")"
    if [[ "$actual" == "$pkg_dir/commands" ]]; then
      rm "$cmd_dst"
      echo -e "${yellow}  Removed commands: $name${reset}"
    else
      echo -e "${yellow}  Skipped commands: $name (symlink points elsewhere: $actual)${reset}"
    fi
  fi

  # Remove skill symlinks (only if they point back to this registry)
  if [[ -d "$pkg_dir/skills" ]]; then
    for skill_file in "$pkg_dir/skills"/*.md; do
      [[ -f "$skill_file" ]] || continue
      local fname
      fname="$(basename "$skill_file")"
      local skill_dst="$CLAUDE_DIR/skills/$fname"
      if [[ -L "$skill_dst" ]]; then
        local actual
        actual="$(resolve_link "$skill_dst")"
        if [[ "$actual" == "$skill_file" ]]; then
          rm "$skill_dst"
          echo -e "${yellow}  Removed skill: $fname${reset}"
        else
          echo -e "${yellow}  Skipped skill: $fname (symlink points elsewhere)${reset}"
        fi
      fi
    done
  fi
}

uninstall_all() {
  for name in $(list_packages); do
    uninstall_package "$name"
  done
  echo "Done."
}

show_status() {
  for name in $(list_packages); do
    local pkg_dir="$REGISTRY_DIR/$name"
    local status=""

    # Check commands
    if [[ -d "$pkg_dir/commands" ]]; then
      local cmd_dst="$CLAUDE_DIR/commands/$name"
      if [[ -L "$cmd_dst" ]]; then
        local actual
        actual="$(resolve_link "$cmd_dst")"
        if [[ "$actual" == "$pkg_dir/commands" ]]; then
          status="commands:${green}linked${reset}"
        else
          status="commands:${yellow}other${reset}"
        fi
      else
        status="commands:${red}missing${reset}"
      fi
    fi

    # Check skills
    if [[ -d "$pkg_dir/skills" ]]; then
      local all_linked=true
      local has_skills=false
      for skill_file in "$pkg_dir/skills"/*.md; do
        [[ -f "$skill_file" ]] || continue
        has_skills=true
        local fname
        fname="$(basename "$skill_file")"
        local skill_dst="$CLAUDE_DIR/skills/$fname"
        if [[ -L "$skill_dst" ]]; then
          local actual
          actual="$(resolve_link "$skill_dst")"
          if [[ "$actual" != "$skill_file" ]]; then
            all_linked=false
            break
          fi
        else
          all_linked=false
          break
        fi
      done
      if ! $has_skills; then
        :  # Empty skills/ dir, skip
      elif $all_linked; then
        status="${status:+$status, }skills:${green}linked${reset}"
      else
        status="${status:+$status, }skills:${red}missing${reset}"
      fi
    fi

    echo -e "  $name  [$status]"
  done
}

# Parse args
if [[ $# -eq 0 ]]; then
  echo "Installing all skill packages..."
  for name in $(list_packages); do
    install_package "$name"
  done
  echo "Done."
elif [[ "$1" == "--uninstall" ]]; then
  if [[ $# -ge 2 ]]; then
    uninstall_package "$2"
  else
    uninstall_all
  fi
elif [[ "$1" == "--status" ]]; then
  show_status
elif [[ "$1" == "--help" || "$1" == "-h" ]]; then
  usage
else
  install_package "$1"
fi
