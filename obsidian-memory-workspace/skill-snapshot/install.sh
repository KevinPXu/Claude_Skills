#!/usr/bin/env bash
# Install obsidian-memory skill + hooks for Claude Code
# Dependencies: bash, grep (that's it)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SKILL_DIR="${CLAUDE_DIR}/skills/obsidian-memory"
VAULT_DIR="${CLAUDE_MEMORY_VAULT:-${CLAUDE_DIR}/memory}"

echo "=== obsidian-memory installer ==="
echo ""

# Install skill
echo "Installing skill..."
mkdir -p "$SKILL_DIR"
cp "${SCRIPT_DIR}/SKILL.md" "$SKILL_DIR/SKILL.md"
echo "  Installed SKILL.md -> $SKILL_DIR/"

# Make scripts executable
chmod +x "${SCRIPT_DIR}/bin/obsidian-memory.sh"
chmod +x "${SCRIPT_DIR}/hooks/context-loader.sh"

# Install hooks config
HOOKS_FILE="${CLAUDE_DIR}/hooks.json"
HOOK_CMD="${SCRIPT_DIR}/hooks/context-loader.sh"

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
  "${SCRIPT_DIR}/bin/obsidian-memory.sh" init
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
