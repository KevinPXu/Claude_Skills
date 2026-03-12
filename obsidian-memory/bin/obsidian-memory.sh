#!/usr/bin/env bash
# obsidian-memory — CLI for Claude's persistent memory graph.
# Thin shim that delegates to the Python/SQLite engine.
#
# Markdown files remain the source of truth. The Python engine maintains
# a SQLite index (.index.db) for fast BM25 search and graph traversal.
# Delete .index.db anytime — it rebuilds automatically.
#
# Usage: obsidian-memory.sh <command> [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAUDE_MEMORY_VAULT="${CLAUDE_MEMORY_VAULT:-$HOME/.claude/memory}"

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 is required but not found." >&2
  echo "Install Python 3.8+ to use obsidian-memory." >&2
  exit 1
fi

exec python3 "${SCRIPT_DIR}/memory_engine.py" "$@"
