#!/usr/bin/env bash
# Install obsidian-memory skill + hooks for Claude Code
# Dependencies: bash, grep (that's it)
set -euo pipefail

usage() {
  echo "Usage: ./install.sh [command] [options]"
  echo ""
  echo "Commands:"
  echo "  (default)              Install skill, hooks, vault, and CLAUDE.md instructions"
  echo "  update                 Re-sync SKILL.md, ensure hook registered, ensure CLAUDE.md updated"
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

# Append memory instructions to a CLAUDE.md file
append_claude_md() {
  local claude_md="$1"
  local memory_marker="## Obsidian Memory"

  if [ -f "$claude_md" ] && grep -qF "$memory_marker" "$claude_md" 2>/dev/null; then
    echo "CLAUDE.md already has memory instructions, skipping."
    return
  fi

  echo "Adding memory instructions to CLAUDE.md..."
  if [ -f "$claude_md" ]; then
    printf '\n' >> "$claude_md"
  fi
  cat >> "$claude_md" << CLAUDEEOF

${memory_marker}

This project uses obsidian-memory for persistent context across conversations. A global \`UserPromptSubmit\` hook automatically loads relevant memory and injects write commands on every prompt. See the "Obsidian Memory Config" block in hook output for available commands.
CLAUDEEOF
  echo "  Updated $claude_md"
}

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

# Derive hooks file and vault locations (shared by install and update)
if [ -n "$HOOKS_PATH" ]; then
  HOOKS_FILE="$HOOKS_PATH"
  HOOKS_DIR="$(cd "$(dirname "$HOOKS_PATH")" && pwd)"
  VAULT_DIR="${HOOKS_DIR}/memory"
else
  HOOKS_FILE="${CLAUDE_DIR}/hooks.json"
  VAULT_DIR="${CLAUDE_MEMORY_VAULT:-${CLAUDE_DIR}/memory}"
fi

# Derive CLAUDE_MD path (shared by install and update)
if [ -n "$HOOKS_PATH" ]; then
  CLAUDE_MD_DIR="$(dirname "$HOOKS_FILE")/.."
  CLAUDE_MD="$(cd "$CLAUDE_MD_DIR" && pwd)/CLAUDE.md"
else
  CLAUDE_MD="${CLAUDE_DIR}/CLAUDE.md"
fi

# Make scripts executable
chmod +x "${SCRIPT_DIR}/bin/obsidian-memory.sh"
chmod +x "${SCRIPT_DIR}/hooks/context-loader.sh"

# Build hook command — set CLAUDE_MEMORY_VAULT so scripts find the right vault
HOOK_CMD="${SCRIPT_DIR}/hooks/context-loader.sh"
if [ -n "$HOOKS_PATH" ]; then
  HOOK_CMD="CLAUDE_MEMORY_VAULT=${VAULT_DIR} ${HOOK_CMD}"
fi

# Install or merge hook into hooks.json
install_hook() {
  local hooks_file="$1"
  local hook_cmd="$2"

  if [ ! -f "$hooks_file" ]; then
    mkdir -p "$(dirname "$hooks_file")"
    echo "Creating hooks.json..."
    cat > "$hooks_file" << HOOKEOF
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${hook_cmd}",
            "timeout": 10,
            "statusMessage": "Loading memory context..."
          }
        ]
      }
    ]
  }
}
HOOKEOF
    echo "  Created $hooks_file"
    return
  fi

  echo "Existing hooks.json found. Merging..."

  if command -v python3 &>/dev/null; then
    python3 - "$hooks_file" "$hook_cmd" << 'PYEOF'
import json, sys

hooks_file, hook_cmd = sys.argv[1], sys.argv[2]

with open(hooks_file) as f:
    config = json.load(f)

new_hook = {
    "type": "command",
    "command": hook_cmd,
    "timeout": 10,
    "statusMessage": "Loading memory context..."
}

if "hooks" not in config:
    config["hooks"] = {}

ups = config["hooks"].setdefault("UserPromptSubmit", [])

# Check if already registered (idempotent)
for group in ups:
    for h in group.get("hooks", []):
        if h.get("command") == hook_cmd:
            print("  Hook already registered, skipping.")
            sys.exit(0)

ups.append({"hooks": [new_hook]})

with open(hooks_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print("  Merged hook into " + hooks_file)
PYEOF
  else
    echo "  python3 not found — add this entry manually under hooks.UserPromptSubmit in $hooks_file:"
    echo ""
    echo "  {"
    echo "    \"hooks\": ["
    echo "      {"
    echo "        \"type\": \"command\","
    echo "        \"command\": \"${hook_cmd}\","
    echo "        \"timeout\": 10,"
    echo "        \"statusMessage\": \"Loading memory context...\""
    echo "      }"
    echo "    ]"
    echo "  }"
  fi
}

# --- Update command ---
if [ "$COMMAND" = "update" ]; then
  echo "=== obsidian-memory update ==="
  echo ""
  echo "Syncing SKILL.md..."
  mkdir -p "$SKILL_DIR"
  cp "${SCRIPT_DIR}/SKILL.md" "$SKILL_DIR/SKILL.md"
  echo "  Copied SKILL.md -> $SKILL_DIR/"
  echo ""
  echo "Ensuring hook is registered..."
  install_hook "$HOOKS_FILE" "$HOOK_CMD"
  echo ""
  append_claude_md "$CLAUDE_MD"
  echo ""
  echo "Done. Scripts are referenced by path and always use the latest version."
  exit 0
fi

# --- Init-vault command ---
if [ "$COMMAND" = "init-vault" ]; then
  PROJECT_ROOT="$(cd "$INIT_VAULT_PATH" && pwd)"
  VAULT_DIR="${PROJECT_ROOT}/.claude/memory"
  CLAUDE_MD="${PROJECT_ROOT}/CLAUDE.md"

  echo "=== obsidian-memory init-vault ==="
  echo ""
  echo "Project: ${PROJECT_ROOT}"
  echo ""

  CLAUDE_MEMORY_VAULT="$VAULT_DIR" "${SCRIPT_DIR}/bin/obsidian-memory.sh" init
  append_claude_md "$CLAUDE_MD"

  echo ""
  echo "=== Done ==="
  echo ""
  echo "Vault:     ${VAULT_DIR}"
  echo "CLAUDE.md: ${CLAUDE_MD}"
  echo ""
  echo "The global hook will auto-discover this vault when working in ${PROJECT_ROOT} or any subdirectory."
  exit 0
fi

# --- Main install ---

echo "=== obsidian-memory installer ==="
echo ""
echo "Scope: $([ -n "$HOOKS_PATH" ] && echo "project (${HOOKS_DIR})" || echo "global (~/.claude)")"
echo ""

# Install skill (always global — Claude Code loads skills from ~/.claude/skills)
echo "Installing skill..."
mkdir -p "$SKILL_DIR"
cp "${SCRIPT_DIR}/SKILL.md" "$SKILL_DIR/SKILL.md"
echo "  Installed SKILL.md -> $SKILL_DIR/"

echo ""
install_hook "$HOOKS_FILE" "$HOOK_CMD"

append_claude_md "$CLAUDE_MD"

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
