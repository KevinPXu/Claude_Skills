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

You have a persistent memory stored as linked markdown files. Notes connect to each
other with `[[wikilinks]]`, forming a knowledge graph. This memory survives across
conversations.

## How It Works

A global `UserPromptSubmit` hook runs on every prompt and handles **reading** automatically:
- Resolves the nearest vault (walks up from cwd to find `.claude/memory/`, falls back to `~/.claude/memory/`)
- Extracts keywords from the user's prompt and searches for relevant notes
- Injects matching context into the conversation
- Injects an **Obsidian Memory Config** block with the resolved vault path and exact commands for writing

The hook also tracks session length and injects save reminders after sustained
conversations or when exit signals are detected.

**Your job is writing.** The hook handles reading, vault resolution, and command setup.
Look for the `--- Obsidian Memory Config ---` block in the conversation — it contains
the exact `$MEM` path and pre-resolved write commands for the current vault. Use those
commands directly instead of hardcoding paths.

Never run `$MEM init`. If no vault exists, ask the user.

---

## What to Remember

The purpose of memory is to let future conversations pick up where past ones left off.
Focus on things that would be painful to re-explain or re-discover:

**Save these — they represent reasoning and decisions:**
- Architectural decisions and *why* they were made ("chose filesystem over API because...")
- User preferences confirmed through actual usage (not guesses)
- Workflows and processes that took multiple iterations to get right
- Project context: tech stack, key files, current state
- Corrections — when the user says "no, always do it this way"
- Debugging insights that required real investigation

**Skip these — they're noise or ephemeral:**
- Generic facts you already know (language syntax, library docs)
- One-off commands or throwaway scripts
- Intermediate steps that led nowhere
- Things obvious from the codebase itself

**The test:** Would a fresh Claude session benefit from knowing this before starting work?
If yes, save it. If it's easily re-discoverable from code or conversation, skip it.

---

## How to Think About the Graph

Each note should be **atomic** — one decision, one pattern, or one concept. Connect
notes with `[[wikilinks]]` so finding one note leads to related context.

Think of it like this: searching for "weather-app" finds the project note, and from
there links lead to the user's preferences, related patterns, and tools they use. The
graph gives you a **trail** to follow, not just isolated facts.

When saving a new note, consider:
1. What category does this belong to? (Project, Pattern, Tool, Preference, Person)
2. What existing notes should this link to?
3. What's the *reasoning*, not just the fact?

---

## Saving Notes

Use the commands from the `--- Obsidian Memory Config ---` block injected by the hook.
Always check if a note already exists before creating one.

### Write a new atomic note

```bash
$MEM search "auth decision"   # check for existing notes first

$MEM write "Projects/weather-app-auth.md" "---
tags: [claude-memory, project]
summary: Weather app chose JWT over session cookies for SPA architecture
---
# Weather App — Auth Decision

## Decision
- JWT over session cookies
- Reason: app is SPA with no server-side rendering

## Links
- [[weather-app]]
- [[Preferences]]"

# Connect to the project index
$MEM link "Projects.md" "Projects/weather-app-auth.md"
```

### Append to an existing note

```bash
$MEM append "Projects/weather-app-auth.md" "
## Update (2026-03-12)
- Added refresh token rotation
- [[auth-refresh-pattern]]"
```

### Link related notes

```bash
$MEM link "Projects/weather-app-auth.md" "Patterns/jwt-pattern.md"
```

### Note format

Keep notes under ~30 lines. The script warns when notes get too large.

Linked notes that aren't direct search hits are loaded as **summaries only**, so always
include a `summary:` field in frontmatter:

```markdown
---
tags: [claude-memory, <category>]
summary: One-line description of what this note captures
---
# Title

## Decision / Context
- What was decided and WHY (the most valuable part)

## Links
- [[Related Note]]
```

**Atomic splitting example**: Instead of one "Auth Decisions" note with JWT choice,
token storage, and refresh strategy, create three notes:
- `Projects/auth-jwt-choice.md` — why JWT over sessions
- `Projects/auth-token-storage.md` — where tokens are stored
- `Projects/auth-refresh-strategy.md` — how refresh works

Each links to the others and to `[[weather-app]]`.

---

## Vault Structure

```
$CLAUDE_MEMORY_VAULT/
  Index.md              # Hub — links to all categories
  Preferences.md        # User prefs, workflow, tools, style
  Projects.md           # Project index
  Projects/<name>.md    # Per-project notes
  Patterns.md           # Pattern index
  Patterns/<name>.md    # Reusable insights
  Tools.md              # Tool index
  Tools/<name>.md       # Tool/framework knowledge
  People.md             # People index
```

---

## When to Act

| Situation | Action |
|---|---|
| User says "remember X" | Save immediately, confirm what was saved |
| User asks "what do you know about..." | Use `$MEM search` or `$MEM context`, summarize findings |
| Important decision made | Save the decision AND the reasoning as an atomic note |
| User corrects you | Update or replace the relevant note |
| Memory Save Reminder appears | Present a **numbered list** of saveable items with one-line descriptions. Ask: "Which would you like me to save? (reply with numbers, e.g. 1,3 or 'all' or 'none')". Only save selected items. |
| Pattern used 2+ times | Create a Pattern note so it's reusable |
