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
#   context <query> [max]       Smart context: search + follow links + read (compact)
#   related <path> [depth]      Follow [[wikilinks]] from a note (graph traversal)
#   tags <tag>                  Find all notes with a given tag
#   init                        Initialize the memory graph structure
#   info                        Show vault location and stats

set -euo pipefail

# --- Config ---
VAULT_DIR="${CLAUDE_MEMORY_VAULT:-$HOME/.claude/memory}"
MAX_CONTEXT_LINES=200  # Cap total context output

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

# Resolve a wikilink name to a file path (relative to vault)
resolve_link() {
  local name="$1"
  # Try exact match first, then case-insensitive
  local found
  found=$(find "$VAULT_DIR" -name "${name}.md" -print -quit 2>/dev/null)
  if [ -z "$found" ]; then
    found=$(find "$VAULT_DIR" -iname "${name}.md" -print -quit 2>/dev/null)
  fi
  if [ -n "$found" ]; then
    echo "${found#$VAULT_DIR/}"
  fi
}

# Extract all [[wikilinks]] from a file, return as resolved paths
extract_links() {
  local filepath="$1"
  grep -oP '\[\[\K[^\]]+' "$filepath" 2>/dev/null | while IFS= read -r link; do
    # Handle [[Name|Display]] format — take the name part
    local name="${link%%|*}"
    resolve_link "$name"
  done | sort -u
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

cmd_related() {
  # Graph traversal: follow [[wikilinks]] from a note up to N depth
  local path="${1:?Usage: obsidian-memory.sh related <path> [depth]}"
  local depth="${2:-1}"
  ensure_vault

  local full
  full=$(note_path "$path")
  if [ ! -f "$full" ]; then
    echo "ERROR: Note not found: $path" >&2
    exit 1
  fi

  # BFS traversal using visited set
  local visited="$path"
  local current_level="$path"
  local level=0

  while [ "$level" -lt "$depth" ] && [ -n "$current_level" ]; do
    local next_level=""
    while IFS= read -r note; do
      local note_full="${VAULT_DIR}/${note}"
      [ -f "$note_full" ] || continue

      local links
      links=$(extract_links "$note_full")
      while IFS= read -r linked; do
        [ -n "$linked" ] || continue
        # Skip if already visited
        if echo "$visited" | grep -qxF "$linked"; then
          continue
        fi
        visited="$visited
$linked"
        next_level="${next_level:+$next_level
}$linked"
      done <<< "$links"
    done <<< "$current_level"

    current_level="$next_level"
    level=$((level + 1))
  done

  # Output all discovered notes (excluding the starting note)
  echo "$visited" | tail -n +2
}

cmd_context() {
  # Smart context: search + follow links + read, with total size cap
  local query="${1:?Usage: obsidian-memory.sh context <query> [max]}"
  local max="${2:-5}"
  ensure_vault

  # Step 1: keyword search for seed notes
  local seed_files
  seed_files=$(ranked_search "$query" "$max")

  if [ -z "$seed_files" ]; then
    echo "No memory notes found for: $query"
    return 0
  fi

  # Step 2: follow links from seed notes (1 level deep) to find related notes
  local all_files="$seed_files"
  while IFS= read -r seed; do
    [ -n "$seed" ] || continue
    local seed_full="${VAULT_DIR}/${seed}"
    [ -f "$seed_full" ] || continue

    local linked
    linked=$(extract_links "$seed_full")
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      # Add if not already in the set
      if ! echo "$all_files" | grep -qxF "$rel"; then
        all_files="$all_files
$rel"
      fi
    done <<< "$linked"
  done <<< "$seed_files"

  # Step 3: output with size cap
  local total_lines=0
  echo "--- Memory Context for: $query ---"

  # Output seed notes first (they're the most relevant)
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    local full="${VAULT_DIR}/${file}"
    [ -f "$full" ] || continue

    local note_lines
    note_lines=$(wc -l < "$full")
    if [ $((total_lines + note_lines)) -gt "$MAX_CONTEXT_LINES" ]; then
      # Include truncated version
      local remaining=$((MAX_CONTEXT_LINES - total_lines))
      if [ "$remaining" -gt 5 ]; then
        echo ""
        echo "## $(basename "$file" .md) [from: $file]"
        head -"$remaining" "$full"
        echo "... (truncated)"
      fi
      break
    fi

    echo ""
    echo "## $(basename "$file" .md) [from: $file]"
    cat "$full"
    total_lines=$((total_lines + note_lines + 2))
  done <<< "$all_files"

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
  related) cmd_related "$@" ;;
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
    echo "  context <query> [max]   Smart context: search + follow links + read"
    echo "  related <path> [depth]  Follow links from a note (graph traversal)"
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
