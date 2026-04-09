#!/usr/bin/env bash
set -euo pipefail

REGISTRY_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v node &>/dev/null; then
  echo "Error: Node.js >= 18 is required. Install it from https://nodejs.org" >&2
  exit 1
fi

# Translate legacy flags to CLI subcommands
translate_args() {
  case "${1:-}" in
    --help|-h)       echo "help" ;;
    --agent)         echo "install --agent $2" ;;
    --skill)         echo "install --skill $2" ;;
    --project)       echo "project $2 ${3:-.}" ;;
    --status)        echo "status" ;;
    --list)          echo "list" ;;
    --uninstall)
      shift
      if [[ $# -eq 0 ]]; then
        echo "uninstall --all"
      elif [[ "$1" == "--agent" ]]; then
        echo "uninstall --agent $2"
      elif [[ "$1" == "--skill" ]]; then
        echo "uninstall --skill $2"
      else
        echo "uninstall $1"
      fi
      ;;
    *)               echo "$@" ;;
  esac
}

if [[ $# -eq 0 ]]; then
  exec node "$REGISTRY_DIR/bin/cli.js" install
else
  TRANSLATED=$(translate_args "$@")
  exec node "$REGISTRY_DIR/bin/cli.js" $TRANSLATED
fi
