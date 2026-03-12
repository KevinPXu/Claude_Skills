#!/usr/bin/env bash
# Hook: context-loader.sh
# Triggered on UserPromptSubmit — extracts keywords from the user's prompt
# and searches the memory vault for relevant context.
#
# Input: JSON on stdin with { "prompt": "...", "cwd": "..." }
# Output: Relevant memory context to stdout (injected into conversation)
#
# Dependencies: bash, grep (no curl, no jq)

set -euo pipefail

MEM="${OBSIDIAN_MEMORY_SCRIPT:-$HOME/Claude_Skills/obsidian-memory/bin/obsidian-memory.sh}"
VAULT="${CLAUDE_MEMORY_VAULT:-$HOME/.claude/memory}"

# Bail early if vault doesn't exist
[ -d "$VAULT" ] || exit 0

# Read stdin — parse prompt without jq
# Uses python if available, falls back to sed
INPUT=$(cat)
if command -v python3 &>/dev/null; then
  PROMPT=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prompt',''))" 2>/dev/null || echo "")
  CWD=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cwd',''))" 2>/dev/null || echo "$PWD")
else
  # Fallback: extract first quoted value after "prompt":
  PROMPT=$(echo "$INPUT" | grep -oP '"prompt"\s*:\s*"\K[^"]*' | head -1)
  CWD=$(echo "$INPUT" | grep -oP '"cwd"\s*:\s*"\K[^"]*' | head -1)
fi
CWD="${CWD:-$PWD}"

if [ -z "$PROMPT" ]; then
  exit 0
fi

# Extract project context from working directory
PROJECT_NAME=$(basename "${CWD}" | tr '_-' ' ')

# Extract meaningful keywords from prompt (skip common stop words)
KEYWORDS=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]' | \
  tr -cs '[:alpha:]' '\n' | \
  grep -vxE '(the|a|an|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|could|should|may|might|shall|can|need|dare|ought|used|to|of|in|for|on|with|at|by|from|as|into|through|during|before|after|above|below|between|out|off|over|under|again|further|then|once|here|there|when|where|why|how|all|both|each|few|more|most|other|some|such|no|nor|not|only|own|same|so|than|too|very|just|because|but|and|or|if|while|about|it|its|this|that|these|those|i|me|my|we|our|you|your|he|him|his|she|her|they|them|their|what|which|who|whom|let|make|get|go|come|take|know|see|think|look|want|give|use|find|tell|ask|work|seem|feel|try|leave|call|keep|put|run|say|turn|help|show|hear|play|move|live|believe|happen|write|provide|sit|stand|lose|pay|meet|include|continue|set|learn|change|lead|understand|watch|follow|stop|create|speak|read|add|spend|grow|open|walk|win|teach|offer|remember|love|consider|appear|buy|wait|serve|die|send|expect|build|stay|fall|cut|reach|kill|remain|suggest|raise|pass|sell|require|report|decide|pull|develop|file|check|fix|implement|update|refactor|debug|test|commit|push|merge|deploy|install|configure|please|could|would|should|hey|hi|hello|thanks|thank|skills|available|right|now|start|yea|lets|also|want|ok|okay)' | \
  head -5 | tr '\n' ' ' | xargs) || true

if [ -z "$KEYWORDS" ]; then
  KEYWORDS="$PROJECT_NAME"
fi

# Search memory for relevant context
RESULTS=$("$MEM" context "$KEYWORDS" 2>/dev/null || echo "")

# If keyword search found nothing, try project name
if ! echo "$RESULTS" | grep -q "^## " && [ -n "$PROJECT_NAME" ] && [ "$KEYWORDS" != "$PROJECT_NAME" ]; then
  RESULTS=$("$MEM" context "$PROJECT_NAME" 2>/dev/null || echo "")
fi

# Only output if we found memory notes
if echo "$RESULTS" | grep -q "^## "; then
  echo "$RESULTS"
fi

exit 0
