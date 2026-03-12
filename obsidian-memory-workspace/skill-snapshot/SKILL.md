---
name: obsidian-memory
description: >
  Graph-based persistent memory stored as linked markdown files. Filesystem-based,
  Obsidian-optional. Automatically searches and loads only relevant context.
  Invoke when user says "remember this", "save this", "what do you know about",
  or asks to recall past context. Also auto-invoked at conversation end to save insights.
tools: Bash
---

# Memory Graph

Filesystem-based persistent memory stored as linked markdown files with `[[wikilinks]]`.
Optionally viewable in Obsidian as a graph.

**Helper script**: `~/Claude_Skills/obsidian-memory/bin/obsidian-memory.sh`
**Vault location**: `~/.claude/memory/` (override with `$CLAUDE_MEMORY_VAULT`)
**Dependencies**: `bash`, `grep` — nothing else

---

## Quick Reference

```bash
MEM=~/Claude_Skills/obsidian-memory/bin/obsidian-memory.sh

# Search for relevant notes (ranked by match count)
$MEM search "keyword"

# Get smart context (search + read top hits, compact)
$MEM context "project name or topic"

# Read a specific note
$MEM read "Preferences.md"

# Write a new note (creates parent dirs automatically)
$MEM write "Projects/MyProject.md" "---
tags: [claude-memory, project]
---
# MyProject
- key decision here
- [[Preferences]]
"

# Append to existing note
$MEM append "Projects/MyProject.md" "- new insight"

# List notes
$MEM list              # root
$MEM list "Projects"   # subfolder

# Link two notes
$MEM link "Projects.md" "Projects/MyProject.md"

# Find notes by tag
$MEM tags "project"

# Vault stats
$MEM info
```

---

## Vault Structure

```
~/.claude/memory/
  .obsidian/            # Open this folder in Obsidian for graph view
  Index.md              # Hub — links to all categories
  Preferences.md        # User prefs (workflow, tools, style)
  Projects.md           # Project index
  Projects/
    <project-name>.md   # Per-project: architecture, decisions, context
  Patterns.md           # Pattern index
  Patterns/
    <pattern-name>.md   # Reusable insights, debugging techniques
  Tools.md              # Tool index
  Tools/
    <tool-name>.md      # Tool/framework knowledge
  People.md             # People index
```

### Note Format

Every note should have:
1. **YAML frontmatter** with `tags` (always include `claude-memory`)
2. **Content** — concise bullet points preferred over prose
3. **Links** — `[[wikilinks]]` to related notes

Example:
```markdown
---
tags: [claude-memory, project]
aliases: [CS5600]
---
# Computer Systems

## Key Decisions
- Using OSTEP textbook
- Homework involves xv6 modifications

## Links
- [[Projects]]
- [[Preferences]]
```

---

## Behavior

### On Conversation Start (Load)
1. Determine the current **project context** from the working directory
2. Run `$MEM context "<project-name>"` to search and load only relevant notes
3. If no match, run `$MEM context "preferences"` for baseline prefs
4. Silently incorporate — don't announce loading unless asked
5. **Never load all notes** — only what's relevant

### On Conversation End (Save)
1. Identify new insights, decisions, preferences, or facts learned
2. Check if a relevant note exists: `$MEM search "<topic>"`
3. If exists: `$MEM append` or read-then-write to update in place
4. If new: `$MEM write` a new atomic note with frontmatter and links
5. Link new notes to their category index: `$MEM link "Projects.md" "Projects/NewProject.md"`
6. Keep notes **atomic** — one topic per note, linked to related topics

### When User Says "Remember This"
1. Save immediately to the appropriate note
2. Create a new note if the topic doesn't exist
3. Add `[[wikilinks]]` to connect to related notes
4. Confirm what was saved

### When User Asks "What Do You Know About X"
1. `$MEM search "X"` to find relevant notes
2. Read the top matches
3. Summarize findings
