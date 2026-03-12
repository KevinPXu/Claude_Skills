#!/usr/bin/env bash
# obsidian-memory — CLI helper for Claude's memory graph
# Filesystem-based, Obsidian-optional. The vault is just a folder of linked markdown files.
#
# Usage: obsidian-memory.sh <command> [args...]
#
# Commands:
#   search <query> [max]        Search memory notes by keyword (grep-based)
#   read <path>                 Read a note (relative to vault root)
#   write <path> <content>      Write/overwrite a note (creates dirs as needed)
#   append <path> <content>     Append content to an existing note
#   list [folder]               List notes in a folder (default: vault root)
#   link <from> <to>            Add a [[wikilink]] from one note to another
#   index                       Read the memory index
#   context <query> [max]       Smart context: search + read top results (compact)
#   tags <tag>                  Find all notes with a given tag
#   init                        Initialize the memory graph structure
#   info                        Show vault location and stats

set -euo pipefail

# --- Config ---
VAULT_DIR="${CLAUDE_MEMORY_VAULT:-$HOME/.claude/memory}"

# --- Helpers ---

ensure_vault() {
  if [ ! -d "$VAULT_DIR" ]; then
    echo "ERROR: Memory vault not found at $VAULT_DIR" >&2
    echo "Run 'obsidian-memory.sh init' to create it." >&2
    exit 1
  fi
}

note_path() {
  echo "${VAULT_DIR}/${1}"
}

# Rank files by number of matches, return top N filenames (relative to vault)
ranked_search() {
  local query="$1"
  local max="${2:-10}"

  # Split query into words, grep for each, count total matches per file
  local words
  IFS=' ' read -ra words <<< "$query"

  local tmp
  tmp=$(mktemp)
  trap "rm -f '$tmp'" RETURN

  for word in "${words[@]}"; do
    # Case-insensitive grep, count matches per file
    grep -ril --include="*.md" "$word" "$VAULT_DIR" 2>/dev/null || true
  done | sort | uniq -c | sort -rn | head -"$max" | awk '{print $2}' > "$tmp"

  # Convert absolute paths to relative
  while IFS= read -r filepath; do
    echo "${filepath#$VAULT_DIR/}"
  done < "$tmp"
}

# --- Commands ---

cmd_search() {
  local query="${1:?Usage: obsidian-memory.sh search <query> [max]}"
  local max="${2:-10}"
  ensure_vault
  ranked_search "$query" "$max"
}

cmd_read() {
  local path="${1:?Usage: obsidian-memory.sh read <path>}"
  ensure_vault
  local full
  full=$(note_path "$path")
  if [ ! -f "$full" ]; then
    echo "ERROR: Note not found: $path" >&2
    exit 1
  fi
  cat "$full"
}

cmd_write() {
  local path="${1:?Usage: obsidian-memory.sh write <path> <content>}"
  local content="${2:?Usage: obsidian-memory.sh write <path> <content>}"
  ensure_vault
  local full
  full=$(note_path "$path")
  mkdir -p "$(dirname "$full")"
  printf '%s\n' "$content" > "$full"
}

cmd_append() {
  local path="${1:?Usage: obsidian-memory.sh append <path> <content>}"
  local content="${2:?Usage: obsidian-memory.sh append <path> <content>}"
  ensure_vault
  local full
  full=$(note_path "$path")
  if [ ! -f "$full" ]; then
    echo "ERROR: Note not found: $path (use 'write' to create)" >&2
    exit 1
  fi
  printf '\n%s\n' "$content" >> "$full"
}

cmd_list() {
  local folder="${1:-.}"
  ensure_vault
  local full="${VAULT_DIR}/${folder}"
  if [ ! -d "$full" ]; then
    echo "ERROR: Folder not found: $folder" >&2
    exit 1
  fi
  find "$full" -maxdepth 1 -name "*.md" -printf '%f\n' 2>/dev/null | sort
}

cmd_link() {
  local from="${1:?Usage: obsidian-memory.sh link <from> <to>}"
  local to="${2:?Usage: obsidian-memory.sh link <from> <to>}"
  ensure_vault
  local link_name
  link_name=$(basename "$to" .md)
  local full
  full=$(note_path "$from")
  if [ ! -f "$full" ]; then
    echo "ERROR: Note not found: $from" >&2
    exit 1
  fi
  # Don't add duplicate links
  if grep -qF "[[${link_name}]]" "$full" 2>/dev/null; then
    return 0
  fi
  printf '\n- [[%s]]\n' "$link_name" >> "$full"
}

cmd_index() {
  ensure_vault
  local idx="${VAULT_DIR}/Index.md"
  if [ ! -f "$idx" ]; then
    echo "ERROR: No Index.md found. Run 'obsidian-memory.sh init' first." >&2
    exit 1
  fi
  cat "$idx"
}

cmd_context() {
  # Smart context: search for a query, read the top matching notes,
  # and output a compact summary suitable for injection into context
  local query="${1:?Usage: obsidian-memory.sh context <query> [max]}"
  local max="${2:-10}"
  ensure_vault

  local files
  files=$(ranked_search "$query" "$max")

  if [ -z "$files" ]; then
    echo "No memory notes found for: $query"
    return 0
  fi

  echo "--- Memory Context for: $query ---"
  while IFS= read -r file; do
    echo ""
    echo "## $(basename "$file" .md)"
    cat "${VAULT_DIR}/${file}" | head -50
  done <<< "$files"
  echo ""
  echo "--- End Memory Context ---"
}

cmd_tags() {
  local tag="${1:?Usage: obsidian-memory.sh tags <tag>}"
  ensure_vault
  # Search for tag in YAML frontmatter
  grep -rl --include="*.md" "tags:.*${tag}" "$VAULT_DIR" 2>/dev/null | while IFS= read -r filepath; do
    echo "${filepath#$VAULT_DIR/}"
  done | sort
}

cmd_init() {
  echo "Initializing memory vault at ${VAULT_DIR}..."
  mkdir -p "$VAULT_DIR"

  # Create .obsidian dir so it can be opened as a vault in Obsidian
  mkdir -p "${VAULT_DIR}/.obsidian"

  # Create Index
  cat > "${VAULT_DIR}/Index.md" << 'EOF'
---
tags: [claude-memory, index]
aliases: [Memory Index]
---
# Claude Memory Index

Central hub for Claude's persistent memory graph.

## Categories
- [[Preferences]] — User preferences, workflow, tools, style
- [[Projects]] — Per-project notes and decisions
- [[Patterns]] — Reusable coding patterns and debugging insights
- [[Tools]] — Tool and framework knowledge
- [[People]] — People and contacts

## Recent
<!-- Auto-updated with recently modified memory notes -->
EOF
  echo "  Created Index.md"

  # Create Preferences
  cat > "${VAULT_DIR}/Preferences.md" << 'EOF'
---
tags: [claude-memory, preferences]
---
# User Preferences

## Workflow

## Communication Style

## Tools

## Links
- [[Index]]
EOF
  echo "  Created Preferences.md"

  # Create category index notes
  for category in Projects Patterns Tools People; do
    mkdir -p "${VAULT_DIR}/${category}"
    cat > "${VAULT_DIR}/${category}.md" << CATEOF
---
tags: [claude-memory, category]
---
# ${category}

## Notes
<!-- Links to ${category,,} notes will be added here -->

## Links
- [[Index]]
CATEOF
    echo "  Created ${category}.md"
  done

  echo ""
  echo "Memory vault initialized at: ${VAULT_DIR}"
  echo ""
  echo "Structure:"
  echo "  Index.md          (hub)"
  echo "  Preferences.md    (user prefs)"
  echo "  Projects/         (project notes)"
  echo "  Projects.md       (project index)"
  echo "  Patterns/         (pattern notes)"
  echo "  Patterns.md       (pattern index)"
  echo "  Tools/            (tool notes)"
  echo "  Tools.md          (tool index)"
  echo "  People/           (people notes)"
  echo "  People.md         (people index)"
  echo "  .obsidian/        (open in Obsidian for graph view)"
}

cmd_info() {
  ensure_vault
  local note_count
  note_count=$(find "$VAULT_DIR" -name "*.md" | wc -l)
  local link_count
  link_count=$(grep -roh '\[\[.*\]\]' "$VAULT_DIR" --include="*.md" 2>/dev/null | wc -l)
  local size
  size=$(du -sh "$VAULT_DIR" 2>/dev/null | cut -f1)

  echo "Memory Vault: ${VAULT_DIR}"
  echo "Notes:        ${note_count}"
  echo "Links:        ${link_count}"
  echo "Size:         ${size}"
}

# --- Main ---
command="${1:-help}"
shift || true

case "$command" in
  search)  cmd_search "$@" ;;
  read)    cmd_read "$@" ;;
  write)   cmd_write "$@" ;;
  append)  cmd_append "$@" ;;
  list)    cmd_list "$@" ;;
  link)    cmd_link "$@" ;;
  index)   cmd_index "$@" ;;
  context) cmd_context "$@" ;;
  tags)    cmd_tags "$@" ;;
  init)    cmd_init "$@" ;;
  info)    cmd_info "$@" ;;
  help|--help|-h)
    echo "Usage: obsidian-memory.sh <command> [args...]"
    echo ""
    echo "Filesystem-based memory graph for Claude. Obsidian-optional."
    echo "Vault location: \$CLAUDE_MEMORY_VAULT (default: ~/.claude/memory)"
    echo ""
    echo "Commands:"
    echo "  search <query> [max]    Search notes by keyword (ranked by relevance)"
    echo "  read <path>             Read a note"
    echo "  write <path> <content>  Write/overwrite a note"
    echo "  append <path> <content> Append to an existing note"
    echo "  list [folder]           List notes in a folder"
    echo "  link <from> <to>        Add a [[wikilink]] between notes"
    echo "  index                   Read the memory index"
    echo "  context <query> [max]   Smart context: search + read top results"
    echo "  tags <tag>              Find notes with a given tag"
    echo "  init                    Initialize the memory vault"
    echo "  info                    Show vault stats"
    ;;
  *)
    echo "Unknown command: $command" >&2
    echo "Run 'obsidian-memory.sh help' for usage." >&2
    exit 1
    ;;
esac
