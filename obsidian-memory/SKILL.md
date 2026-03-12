---
name: obsidian-memory
description: >
  Persistent memory graph for Claude — stores decisions, reasoning, preferences, and
  project context as linked markdown notes so they survive across conversations. Use this
  skill whenever the user says "remember this", "save this", "what do you know about",
  "last time we discussed", "what did we decide", or asks to recall anything from a
  previous session. Also use when starting work in a project directory (to load project
  context), when the user corrects a recurring mistake, when important architectural
  decisions are made, or when wrapping up a conversation that produced reusable insights.
  If in doubt about whether to save something, lean toward saving it — forgetting is
  worse than a few extra notes.
tools: Bash
---

# Memory Graph

You have a persistent memory stored as linked markdown files at `~/.claude/memory/`.
Notes connect to each other with `[[wikilinks]]`, forming a knowledge graph you can
search and traverse. This memory survives across conversations.

**Helper script**: `~/Claude_Skills/obsidian-memory/bin/obsidian-memory.sh`
(Referred to as `$MEM` below)

```bash
MEM=~/Claude_Skills/obsidian-memory/bin/obsidian-memory.sh
```

---

## What to Remember

The purpose of memory is to let future conversations pick up where past ones left off.
Focus on capturing things that would be painful to re-explain or re-discover:

**Save these — they represent reasoning and decisions:**
- Architectural decisions and *why* they were made ("chose filesystem over API because...")
- User preferences confirmed through actual usage (not guesses)
- Workflows and processes that took multiple iterations to get right
- Project context: tech stack, directory structure, key files, current state
- Corrections — when the user says "no, always do it this way"
- Debugging insights that required real investigation

**Skip these — they're noise or ephemeral:**
- Generic facts you already know (language syntax, library docs)
- One-off commands or throwaway scripts
- Intermediate steps that led nowhere
- Things that are obvious from the codebase itself

**The test for whether to save something:** Would a fresh Claude session benefit from
knowing this before starting work? If yes, save it. If the information is easily
re-discoverable from the code or conversation, skip it.

---

## How to Think About the Graph

Each note should be **atomic** — one topic, one decision, one project. Connect notes
with `[[wikilinks]]` so that finding one note leads you to related context.

Think of it like this: when you search for "CS5600", you should find the project note,
and from there you can follow links to the user's preferences, related patterns, and
tools they use. The graph gives you a **trail** to follow, not just isolated facts.

When saving a new note:
1. What category does this belong to? (Project, Pattern, Tool, Preference, Person)
2. What existing notes should this link to?
3. What's the *reasoning* behind this, not just the fact?

---

## Loading Context

When you need to recall something, search first, then follow links:

```bash
# Search by keyword — returns notes ranked by relevance
$MEM context "search terms"

# This does: keyword search → follow [[wikilinks]] 1 level deep → read all hits
# Output is capped at 200 lines to avoid flooding context

# For targeted lookup:
$MEM search "topic"         # just filenames
$MEM read "Projects/X.md"   # read a specific note
$MEM related "Projects/X.md" 2  # follow links 2 levels deep
```

**On conversation start:** Determine the project from the working directory, then run
`$MEM context "<project>"`. If no project match, try `$MEM context "preferences"`.
Incorporate what you find silently — don't announce that you're loading memory.

**Mid-conversation:** If the user references past work or decisions, search for it.
Follow links from the results to build a fuller picture.

---

## Saving Context

When you learn something worth remembering:

```bash
# Check if a note already exists
$MEM search "topic"

# Create a new note (directories are created automatically)
$MEM write "Projects/weather-app.md" "---
tags: [claude-memory, project]
---
# Weather App

## Decisions
- React + TypeScript chosen for frontend
- Reason: user's team already uses React, TS adds safety for API types

## Stack
- Frontend: React 18, TypeScript, Vite
- API: OpenWeatherMap (free tier)

## Links
- [[Projects]]
- [[Preferences]]
"

# Add to an existing note
$MEM append "Projects/weather-app.md" "## Auth Decision (2026-03-11)
- Chose JWT over session cookies
- Reason: app is SPA, no server-side rendering needed
- [[Patterns]]"

# Connect it to the category index
$MEM link "Projects.md" "Projects/weather-app.md"

# Link between related notes
$MEM link "Projects/weather-app.md" "Tools/React.md"
```

### Note Format

```markdown
---
tags: [claude-memory, <category>]
aliases: [alternate names for search]
---
# Title

## Context / Decisions
- What was decided and WHY (this is the most valuable part)

## Details
- Specifics, configurations, key paths

## Links
- [[Related Note]]
```

---

## Vault Structure

```
~/.claude/memory/
  Index.md              # Hub — links to all categories
  Preferences.md        # User prefs: workflow, tools, style
  Projects.md           # Project index
  Projects/<name>.md    # Per-project notes
  Patterns.md           # Pattern index
  Patterns/<name>.md    # Reusable insights, debugging techniques
  Tools.md              # Tool index
  Tools/<name>.md       # Tool/framework knowledge
  People.md             # People index
```

---

## Command Reference

| Command | Description |
|---|---|
| `$MEM search <query> [max]` | Keyword search, ranked by relevance |
| `$MEM context <query> [max]` | Search + follow links + read (smart context) |
| `$MEM read <path>` | Read a specific note |
| `$MEM write <path> <content>` | Create/overwrite a note |
| `$MEM append <path> <content>` | Append to existing note |
| `$MEM list [folder]` | List notes in a folder |
| `$MEM link <from> <to>` | Add a `[[wikilink]]` between notes |
| `$MEM related <path> [depth]` | Follow links from a note (graph traversal) |
| `$MEM tags <tag>` | Find notes by tag |
| `$MEM index` | Read the hub note |
| `$MEM info` | Vault stats |
| `$MEM init` | Initialize vault structure |

---

## Behavior Summary

| Situation | Action |
|---|---|
| Conversation start | `$MEM context "<project>"` based on working directory |
| User says "remember X" | Save immediately, confirm what was saved |
| User asks "what do you know" | Search, follow links, summarize |
| Important decision made | Save the decision AND the reasoning |
| User corrects you | Update the relevant note, remove wrong info |
| Conversation end | Save new insights if any are worth keeping |
| Pattern used 2+ times | Create a Pattern note so it's reusable |
