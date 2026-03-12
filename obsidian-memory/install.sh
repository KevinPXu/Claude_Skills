#!/usr/bin/env bash
# Install obsidian-memory skill + hooks for Claude Code
# Dependencies: bash, grep (that's it)
set -euo pipefail

usage() {
  echo "Usage: ./install.sh [command] [options]"
  echo ""
  echo "Commands:"
  echo "  (default)              Install skill, hooks, vault, and CLAUDE.md instructions"
  echo "  update                 Re-sync SKILL.md to ~/.claude/skills/ from source"
  echo "  init-vault <path>      Create a project-local vault and add CLAUDE.md instructions"
  echo "                         <path> is the project root (vault goes in <path>/.claude/memory/)"
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
COMMAND="install"
INIT_VAULT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    update)
      COMMAND="update"
      shift
      ;;
    init-vault)
      COMMAND="init-vault"
      INIT_VAULT_PATH="${2:?Usage: ./install.sh init-vault <project-path>}"
      shift 2
      ;;
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

# --- Update command ---
if [ "$COMMAND" = "update" ]; then
  echo "=== obsidian-memory update ==="
  echo ""
  echo "Syncing SKILL.md..."
  mkdir -p "$SKILL_DIR"
  cp "${SCRIPT_DIR}/SKILL.md" "$SKILL_DIR/SKILL.md"
  echo "  Copied SKILL.md -> $SKILL_DIR/"
  echo ""
  echo "Done. Hooks and scripts are referenced by path and always use the latest version."
  exit 0
fi

# --- Init-vault command ---
if [ "$COMMAND" = "init-vault" ]; then
  PROJECT_ROOT="$(cd "$INIT_VAULT_PATH" && pwd)"
  VAULT_DIR="${PROJECT_ROOT}/.claude/memory"
  CLAUDE_MD="${PROJECT_ROOT}/CLAUDE.md"
  MEMORY_MARKER="## Obsidian Memory"

  echo "=== obsidian-memory init-vault ==="
  echo ""
  echo "Project: ${PROJECT_ROOT}"
  echo ""

  # Initialize vault
  CLAUDE_MEMORY_VAULT="$VAULT_DIR" "${SCRIPT_DIR}/bin/obsidian-memory.sh" init

  # Add CLAUDE.md instructions
  if [ -f "$CLAUDE_MD" ] && grep -qF "$MEMORY_MARKER" "$CLAUDE_MD" 2>/dev/null; then
    echo "CLAUDE.md already has memory instructions, skipping."
  else
    echo "Adding memory instructions to CLAUDE.md..."
    if [ -f "$CLAUDE_MD" ]; then
      printf '\n' >> "$CLAUDE_MD"
    fi
    cat >> "$CLAUDE_MD" << CLAUDEEOF

${MEMORY_MARKER}

This project uses obsidian-memory for persistent context across conversations.

**Setup (run at conversation start):**
\`\`\`bash
MEM=${SCRIPT_DIR}/bin/obsidian-memory.sh

# Resolve vault: project-local first, then global
if [ -d ".claude/memory" ]; then
  export CLAUDE_MEMORY_VAULT="\$(pwd)/.claude/memory"
elif [ -d "\$HOME/.claude/memory" ]; then
  export CLAUDE_MEMORY_VAULT="\$HOME/.claude/memory"
fi
\`\`\`

**Key commands:**
- \`\$MEM context "<query>"\` — search + follow links + read relevant notes
- \`\$MEM write "<path>" "<content>"\` — save a new note
- \`\$MEM append "<path>" "<content>"\` — add to existing note
- \`\$MEM link "<from>" "<to>"\` — connect notes with wikilinks
- \`\$MEM search "<query>"\` — find notes by keyword

**When to save:** Architectural decisions (with reasoning), user corrections, project context, workflow preferences, debugging insights worth keeping.

**When NOT to save:** Generic facts, one-off commands, things obvious from the codebase.

**Memory Save Reminder:** When a "Memory Save Reminder" appears in context, ask the user if they'd like to save insights from the session. Do not save automatically — wait for confirmation.
CLAUDEEOF
    echo "  Updated $CLAUDE_MD"
  fi

  echo ""
  echo "=== Done ==="
  echo ""
  echo "Vault:     ${VAULT_DIR}"
  echo "CLAUDE.md: ${CLAUDE_MD}"
  echo ""
  echo "The global hook will auto-discover this vault when working in ${PROJECT_ROOT} or any subdirectory."
  exit 0
fi

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

# Add key instructions to CLAUDE.md
if [ -n "$HOOKS_PATH" ]; then
  CLAUDE_MD_DIR="$(dirname "$HOOKS_FILE")/.."
  CLAUDE_MD="$(cd "$CLAUDE_MD_DIR" && pwd)/CLAUDE.md"
else
  CLAUDE_MD="${CLAUDE_DIR}/CLAUDE.md"
fi

MEMORY_MARKER="## Obsidian Memory"

if [ -f "$CLAUDE_MD" ] && grep -qF "$MEMORY_MARKER" "$CLAUDE_MD" 2>/dev/null; then
  echo "CLAUDE.md already has memory instructions, skipping."
else
  echo "Adding memory instructions to CLAUDE.md..."
  # Add a newline separator if appending to existing file
  if [ -f "$CLAUDE_MD" ]; then
    printf '\n' >> "$CLAUDE_MD"
  fi
  cat >> "$CLAUDE_MD" << CLAUDEEOF

${MEMORY_MARKER}

This project uses obsidian-memory for persistent context across conversations.

**Setup (run at conversation start):**
\`\`\`bash
MEM=${SCRIPT_DIR}/bin/obsidian-memory.sh

# Resolve vault: project-local first, then global
if [ -d ".claude/memory" ]; then
  export CLAUDE_MEMORY_VAULT="\$(pwd)/.claude/memory"
elif [ -d "\$HOME/.claude/memory" ]; then
  export CLAUDE_MEMORY_VAULT="\$HOME/.claude/memory"
fi
\`\`\`

**Key commands:**
- \`\$MEM context "<query>"\` — search + follow links + read relevant notes
- \`\$MEM write "<path>" "<content>"\` — save a new note
- \`\$MEM append "<path>" "<content>"\` — add to existing note
- \`\$MEM link "<from>" "<to>"\` — connect notes with wikilinks
- \`\$MEM search "<query>"\` — find notes by keyword

**When to save:** Architectural decisions (with reasoning), user corrections, project context, workflow preferences, debugging insights worth keeping.

**When NOT to save:** Generic facts, one-off commands, things obvious from the codebase.

**Memory Save Reminder:** When a "Memory Save Reminder" appears in context, ask the user if they'd like to save insights from the session. Do not save automatically — wait for confirmation.
CLAUDEEOF
  echo "  Updated $CLAUDE_MD"
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
echo "CLAUDE.md:     ${CLAUDE_MD}"
echo ""
echo "Optional: Open ${VAULT_DIR} in Obsidian to visualize the graph."
