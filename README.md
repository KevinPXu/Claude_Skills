# Claude Skills

A collection of custom skills and hooks for [Claude Code](https://claude.ai/code).

## Skills

### obsidian-memory

Graph-based persistent memory for Claude Code, stored as linked markdown files on disk. Optionally viewable in [Obsidian](https://obsidian.md) as a knowledge graph.

**Features:**
- **Graph-based memory** — Atomic notes connected with `[[wikilinks]]`
- **Search-first loading** — Only loads relevant context via grep-based ranked search
- **Auto-context hooks** — Automatically pulls relevant memory on each prompt via `UserPromptSubmit` hook
- **Auto vault resolution** — Walks up from working directory to find the nearest `.claude/memory/` vault
- **Session tracking** — Prompts to save memory after sustained conversations or on exit signals
- **Project-scoped or global** — One global install, per-project vaults where you want them
- **Cross-platform** — Works on macOS, Linux, and Windows (Git Bash/WSL/MSYS2)
- **Zero dependencies** — Just `bash` and `grep`. No Obsidian, curl, or jq required
- **Obsidian-optional** — Open the vault folder in Obsidian anytime for graph visualization

#### Install

```bash
cd obsidian-memory
./install.sh
```

This sets up everything globally:
- **Skill** → `~/.claude/skills/obsidian-memory/SKILL.md`
- **Hook** → `~/.claude/hooks.json` (fires on every prompt, auto-discovers vaults)
- **Vault** → `~/.claude/memory/` (default global vault)
- **CLAUDE.md** → `~/.claude/CLAUDE.md` (key instructions always in context)

#### Create a project-local vault

If you want a project to have its own isolated memory:

```bash
./install.sh init-vault /path/to/project
```

This creates:
- **Vault** → `/path/to/project/.claude/memory/`
- **CLAUDE.md** → Appends memory instructions to `/path/to/project/CLAUDE.md`

The global hook auto-discovers project-local vaults by walking up from the working directory. No extra hook config needed.

#### Update after source changes

Run after pulling new changes or on a system where the hook wasn't auto-registered:

```bash
./install.sh update
```

This re-syncs `SKILL.md`, ensures the hook is registered in `hooks.json` (merging if needed), and ensures `CLAUDE.md` has memory instructions. Hooks and scripts are referenced by path from the source repo and always use the latest version. Safe to re-run — all steps are idempotent.

#### Vault resolution order

When the hook fires, it resolves the vault in this order:

1. `CLAUDE_MEMORY_VAULT` env var (if set explicitly)
2. Walk up from working directory looking for `.claude/memory/`
3. Fall back to `~/.claude/memory/`

#### Memory saving behavior

- **Manual** — Say "remember this", "save this", etc. and Claude invokes the skill to save
- **Periodic reminder** — After every 10 prompts (configurable via `OBSIDIAN_MEMORY_REMINDER_THRESHOLD`), Claude asks if you want to save session insights
- **Exit reminder** — When `/exit`, `/clear`, `/quit`, or natural language exit signals ("bye", "I'm done", etc.) are detected, Claude asks before wrapping up
- **Always user-confirmed** — Claude never saves automatically; it asks first and waits for confirmation

#### Vault structure

```
.claude/memory/
  Index.md              # Hub — links to all categories
  Preferences.md        # User prefs: workflow, tools, style
  Projects.md           # Project index
  Projects/<name>.md    # Per-project notes
  Patterns.md           # Pattern index
  Patterns/<name>.md    # Reusable insights, debugging techniques
  Tools.md              # Tool index
  Tools/<name>.md       # Tool/framework knowledge
  People.md             # People index
  .obsidian/            # Open in Obsidian for graph view
```

#### Command reference

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

See [obsidian-memory/SKILL.md](obsidian-memory/SKILL.md) for full usage docs.

## Requirements

- [Claude Code](https://claude.ai/code)
- `bash`, `grep`

## License

See [LICENSE](LICENSE).
