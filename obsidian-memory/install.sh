#!/usr/bin/env bash
# Install obsidian-memory skill + hooks for Claude Code
# Dependencies: bash, grep (that's it)
set -euo pipefail

usage() {
  echo "Usage: ./install.sh [--hooks-path <path>]"
  echo ""
  echo "Options:"
  echo "  --hooks-path <path>  Path to hooks.json (default: ~/.claude/hooks.json)"
  echo "                       Use a project .claude/hooks.json for project-scoped install."
  echo "                       The memory vault will be created alongside hooks.json."
  echo "  -h, --help           Show this help message"
  exit 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SKILL_DIR="${CLAUDE_DIR}/skills/obsidian-memory"
HOOKS_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hooks-path)
      HOOKS_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# Derive vault and hooks locations from --hooks-path
if [ -n "$HOOKS_PATH" ]; then
  HOOKS_FILE="$HOOKS_PATH"
  HOOKS_DIR="$(cd "$(dirname "$HOOKS_PATH")" && pwd)"
  VAULT_DIR="${HOOKS_DIR}/memory"
else
  HOOKS_FILE="${CLAUDE_DIR}/hooks.json"
  VAULT_DIR="${CLAUDE_MEMORY_VAULT:-${CLAUDE_DIR}/memory}"
fi

echo "=== obsidian-memory installer ==="
echo ""
echo "Scope: $([ -n "$HOOKS_PATH" ] && echo "project (${HOOKS_DIR})" || echo "global (~/.claude)")"
echo ""

# Install skill (always global — Claude Code loads skills from ~/.claude/skills)
echo "Installing skill..."
mkdir -p "$SKILL_DIR"
cp "${SCRIPT_DIR}/SKILL.md" "$SKILL_DIR/SKILL.md"
echo "  Installed SKILL.md -> $SKILL_DIR/"

# Make scripts executable
chmod +x "${SCRIPT_DIR}/bin/obsidian-memory.sh"
chmod +x "${SCRIPT_DIR}/hooks/context-loader.sh"

# Build hook command — set CLAUDE_MEMORY_VAULT so scripts find the right vault
HOOK_CMD="${SCRIPT_DIR}/hooks/context-loader.sh"
if [ -n "$HOOKS_PATH" ]; then
  HOOK_CMD="CLAUDE_MEMORY_VAULT=${VAULT_DIR} ${HOOK_CMD}"
fi

# Install hooks config
if [ -f "$HOOKS_FILE" ]; then
  echo ""
  echo "Existing hooks.json found at $HOOKS_FILE"
  echo "To add the memory hook manually, add this entry under hooks.UserPromptSubmit:"
  echo ""
  echo "  {"
  echo "    \"hooks\": ["
  echo "      {"
  echo "        \"type\": \"command\","
  echo "        \"command\": \"${HOOK_CMD}\","
  echo "        \"timeout\": 10,"
  echo "        \"statusMessage\": \"Loading memory context...\""
  echo "      }"
  echo "    ]"
  echo "  }"
else
  mkdir -p "$(dirname "$HOOKS_FILE")"
  echo "Creating hooks.json..."
  cat > "$HOOKS_FILE" << HOOKEOF
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${HOOK_CMD}",
            "timeout": 10,
            "statusMessage": "Loading memory context..."
          }
        ]
      }
    ]
  }
}
HOOKEOF
  echo "  Created $HOOKS_FILE"
fi

# Initialize memory vault
echo ""
read -p "Initialize memory vault at ${VAULT_DIR}? (Y/n): " init_vault
if [[ ! "$init_vault" =~ ^[Nn] ]]; then
  CLAUDE_MEMORY_VAULT="$VAULT_DIR" "${SCRIPT_DIR}/bin/obsidian-memory.sh" init
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Helper script: ${SCRIPT_DIR}/bin/obsidian-memory.sh"
echo "Memory vault:  ${VAULT_DIR}"
echo "Skill:         ${SKILL_DIR}/SKILL.md"
echo "Hook:          ${HOOKS_FILE}"
echo ""
echo "Optional: Open ${VAULT_DIR} in Obsidian to visualize the graph."
