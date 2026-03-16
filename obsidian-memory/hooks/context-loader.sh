#!/usr/bin/env bash
# Hook: context-loader.sh
# Triggered on SessionStart and UserPromptSubmit.
#
# SessionStart: ensures a vault pointer exists in the project's built-in
#   auto-memory (so vault survives /clear), then injects vault config.
# UserPromptSubmit: extracts keywords from the user's prompt, searches the
#   vault for relevant context, and tracks session length for save reminders.
#
# Input: JSON on stdin with { "prompt": "...", "cwd": "..." }
# Output: Relevant memory context to stdout (injected into conversation)
#
# Dependencies: bash, grep (no curl, no jq)

set -euo pipefail

MEM="${OBSIDIAN_MEMORY_SCRIPT:-$HOME/Claude_Skills/obsidian-memory/bin/obsidian-memory.sh}"

# --- Vault resolution ---
# If CLAUDE_MEMORY_VAULT is set explicitly, use it.
# Otherwise, walk up from cwd looking for a .claude/memory/ directory.
# Fall back to global ~/.claude/memory/ if nothing found.
resolve_vault() {
  if [ -n "${CLAUDE_MEMORY_VAULT:-}" ]; then
    echo "$CLAUDE_MEMORY_VAULT"
    return
  fi

  local dir="${1:-$PWD}"
  while [ "$dir" != "/" ]; do
    if [ -d "$dir/.claude/memory" ]; then
      echo "$dir/.claude/memory"
      return
    fi
    dir=$(dirname "$dir")
  done

  echo "$HOME/.claude/memory"
}

# Read stdin first so we can use cwd for vault resolution
INPUT=$(cat)
if command -v python3 &>/dev/null; then
  PROMPT=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prompt',''))" 2>/dev/null || echo "")
  CWD=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cwd',''))" 2>/dev/null || echo "$PWD")
else
  # Fallback: extract first quoted value after "prompt":
  PROMPT=$(echo "$INPUT" | sed -n 's/.*"prompt" *: *"\([^"]*\)".*/\1/p' | head -1)
  CWD=$(echo "$INPUT" | sed -n 's/.*"cwd" *: *"\([^"]*\)".*/\1/p' | head -1)
fi
CWD="${CWD:-$PWD}"

# Resolve vault using the actual working directory from the prompt
VAULT="$(resolve_vault "$CWD")"
export CLAUDE_MEMORY_VAULT="$VAULT"

# Bail early if vault doesn't exist
[ -d "$VAULT" ] || exit 0

# --- Ensure vault pointer in project auto-memory ---
# Creates a persistent obsidian-vault.md stub + MEMORY.md entry so the vault
# survives /clear. Runs at both SessionStart and UserPromptSubmit (idempotent).
_ensure_vault_pointer() {
  local vault="$1"
  local cwd="$2"

  local project_key
  project_key=$(echo "$cwd" | tr '/' '-')
  local auto_memory_dir="$HOME/.claude/projects/$project_key/memory"

  [ -d "$auto_memory_dir" ] || return 0

  local stub_path="$auto_memory_dir/obsidian-vault.md"
  local memory_index="$auto_memory_dir/MEMORY.md"

  # Write/refresh stub if missing or vault path changed
  if [ ! -f "$stub_path" ] || ! grep -qF "$vault" "$stub_path" 2>/dev/null; then
    printf -- '---\nname: obsidian-vault\ndescription: Obsidian memory vault at %s — always search here for code reviews, project decisions, and past context\ntype: reference\n---\n\nVault path: %s\nSearch with: $MEM search <query>\n' "$vault" "$vault" > "$stub_path"
  fi

  # Add MEMORY.md entry if missing
  if [ -f "$memory_index" ] && ! grep -qF "[obsidian-vault.md]" "$memory_index" 2>/dev/null; then
    printf -- '\n- [obsidian-vault.md](obsidian-vault.md) - Obsidian memory vault at %s — always search here for code reviews, project decisions, and past context\n' "$vault" >> "$memory_index"
  fi
}

_ensure_vault_pointer "$VAULT" "$CWD" 2>/dev/null || true

# --- Session tracking ---
SESSION_FILE="${VAULT}/.session-count"
SAVE_REMINDER_THRESHOLD="${OBSIDIAN_MEMORY_REMINDER_THRESHOLD:-5}"

# Increment prompt count
if [ -f "$SESSION_FILE" ]; then
  COUNT=$(cat "$SESSION_FILE" 2>/dev/null || echo "0")
  COUNT=$((COUNT + 1))
else
  COUNT=1
fi
printf '%s' "$COUNT" > "$SESSION_FILE"

# SessionStart: no prompt — inject vault config so Claude knows vault is available
if [ -z "$PROMPT" ]; then
  echo ""
  echo "--- Obsidian Memory Config ---"
  echo "Vault: ${VAULT}"
  echo "MEM=${MEM}"
  echo "Save:   CLAUDE_MEMORY_VAULT=\"${VAULT}\" \$MEM write \"<path>\" \"<content>\""
  echo "Search: CLAUDE_MEMORY_VAULT=\"${VAULT}\" \$MEM search \"<query>\""
  echo "One decision per note. Add summary: to frontmatter."
  echo "--- End Config ---"
  exit 0
fi

# --- Detect session-ending signals ---
PROMPT_LOWER=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')
IS_EXIT=false

# Slash commands
case "$PROMPT_LOWER" in
  /exit|/clear|/quit|/compact) IS_EXIT=true ;;
esac

# Natural language exit signals (only match short prompts to avoid false positives)
if [ "${#PROMPT}" -lt 50 ]; then
  case "$PROMPT_LOWER" in
    bye|goodbye|"i'm done"|"im done"|"that's all"|"thats all"|"all done"|"wrap up"|"wrapping up"|"signing off"|"log off") IS_EXIT=true ;;
  esac
fi

if [ "$IS_EXIT" = true ] && [ "$COUNT" -gt 1 ]; then
  echo ""
  echo "--- Memory Save Reminder ---"
  echo "The user is ending this session (${COUNT} exchanges)."
  echo "Review the conversation for saveable decisions, insights, or context."
  echo "Present them as a NUMBERED LIST with one-line descriptions, e.g.:"
  echo "  1. [decision] Chose PPR+Steiner for graph traversal"
  echo "  2. [finding] Hook stderr not visible to user in Claude Code"
  echo "  3. [preference] User wants terse commit messages"
  echo "Then ask: \"Which would you like me to save? (reply with numbers, e.g. 1,3 or 'all' or 'none')\""
  echo "Only save the items the user selects. Do not exit or clear until the user responds."
  echo "--- End Reminder ---"
  exit 0
fi

# Extract project context from working directory
PROJECT_NAME=$(basename "${CWD}" | tr '_-' ' ')

# Extract meaningful keywords from prompt (skip common stop words)
# Strip apostrophes first so "what's" becomes "whats" not "what" + "s"
KEYWORDS=$(echo "$PROMPT" | tr -d "'" | tr '[:upper:]' '[:lower:]' | \
  tr -cs '[:alpha:]' '\n' | \
  grep -vxE '(.{1,2}|the|a|an|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|could|should|may|might|shall|can|need|dare|ought|used|to|of|in|for|on|with|at|by|from|as|into|through|during|before|after|above|below|between|out|off|over|under|again|further|then|once|here|there|when|where|why|how|all|both|each|few|more|most|other|some|such|no|nor|not|only|own|same|so|than|too|very|just|because|but|and|or|if|while|about|it|its|this|that|these|those|i|me|my|we|our|you|your|he|him|his|she|her|they|them|their|what|which|who|whom|let|make|get|go|come|take|know|see|think|look|want|give|use|find|tell|ask|work|seem|feel|try|leave|call|keep|put|run|say|turn|help|show|hear|play|move|live|believe|happen|write|provide|sit|stand|lose|pay|meet|include|continue|set|learn|change|lead|understand|watch|follow|stop|speak|read|add|spend|grow|open|walk|win|teach|offer|remember|love|consider|appear|buy|wait|serve|die|send|expect|stay|fall|cut|reach|kill|remain|suggest|raise|pass|sell|require|report|decide|pull|please|could|would|should|hey|hi|hello|thanks|thank|skills|available|right|now|start|yea|lets|also|want|ok|okay)' | \
  head -5 | tr '\n' ' ' | xargs) || true

if [ -z "$KEYWORDS" ]; then
  KEYWORDS="$PROJECT_NAME"
fi

# Search memory for relevant context
RESULTS=$("$MEM" context "$KEYWORDS" 2>/dev/null || echo "")

# Count how many notes were found (context headers contain "[from:" or "[linked,")
NOTE_COUNT=0
if echo "$RESULTS" | grep -q "^## "; then
  NOTE_COUNT=$(echo "$RESULTS" | grep -c "\[from:" || true)
  echo ""
  echo "## Relevant Memory Notes"
  echo ""
  echo "$RESULTS"
fi

# --- Status line ---
# stdout: injected into Claude's context
echo ""
echo "--- Memory Hook Status ---"
echo "Vault:    ${VAULT}"
echo "Keywords: ${KEYWORDS}"
echo "Notes:    ${NOTE_COUNT} found"
echo "Session:  prompt #${COUNT}"
echo "--- End Status ---"

# Note: hook stdout is injected into Claude's context (not shown to user).
# The user sees only the statusMessage from hooks.json during execution.

# --- Inject write config when notes were found or save reminders triggered ---
# Skip the full config block on prompts with no memory relevance to save tokens.
# The obsidian-memory skill will still trigger when needed and can inject config then.
if [ "$NOTE_COUNT" -gt 0 ] || [ "$COUNT" -ge "$SAVE_REMINDER_THRESHOLD" ]; then
  echo ""
  echo "--- Obsidian Memory Config ---"
  echo "MEM=${MEM}"
  echo "export CLAUDE_MEMORY_VAULT=\"${VAULT}\""
  echo "Save:   CLAUDE_MEMORY_VAULT=\"${VAULT}\" \$MEM write \"<path>\" \"<content>\""
  echo "Append: CLAUDE_MEMORY_VAULT=\"${VAULT}\" \$MEM append \"<path>\" \"<content>\""
  echo "Link:   CLAUDE_MEMORY_VAULT=\"${VAULT}\" \$MEM link \"<from>\" \"<to>\""
  echo "Search: CLAUDE_MEMORY_VAULT=\"${VAULT}\" \$MEM search \"<query>\""
  echo "One decision per note. Link related decisions with [[wikilinks]]. Add summary: to frontmatter."
  echo "Ask user before saving. Never run \$MEM init."
  echo "--- End Config ---"
fi

# After enough exchanges, remind Claude to offer saving
if [ "$COUNT" -ge "$SAVE_REMINDER_THRESHOLD" ] && [ $((COUNT % SAVE_REMINDER_THRESHOLD)) -eq 0 ]; then
  echo ""
  echo "--- Memory Save Reminder ---"
  echo "This session has had ${COUNT} exchanges."
  echo "Review the conversation for saveable decisions, insights, or context."
  echo "Present them as a NUMBERED LIST with one-line descriptions, e.g.:"
  echo "  1. [decision] Chose PPR+Steiner for graph traversal"
  echo "  2. [finding] Hook stderr not visible to user in Claude Code"
  echo "  3. [preference] User wants terse commit messages"
  echo "Then ask: \"Which would you like me to save? (reply with numbers, e.g. 1,3 or 'all' or 'none')\""
  echo "Only save the items the user selects."
  echo "--- End Reminder ---"
fi

exit 0
