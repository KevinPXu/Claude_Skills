# Claude Skills

A collection of custom skills and hooks for [Claude Code](https://claude.com/claude-code).

## Skills

### obsidian-memory

Graph-based persistent memory for Claude Code, stored as linked markdown files on disk. Optionally viewable in [Obsidian](https://obsidian.md) as a knowledge graph.

**Features:**
- **Graph-based memory** — Atomic notes connected with `[[wikilinks]]`
- **Search-first loading** — Only loads relevant context via grep-based ranked search
- **Auto-context hooks** — Automatically pulls relevant memory on each prompt
- **Zero dependencies** — Just `bash` and `grep`. No Obsidian, curl, or jq required
- **Obsidian-optional** — Open the vault folder in Obsidian anytime for graph visualization

**Quick start:**
```bash
cd obsidian-memory
./install.sh
```

**Manual setup:**
```bash
# Initialize the memory vault
./bin/obsidian-memory.sh init

# Copy skill to Claude Code
cp SKILL.md ~/.claude/skills/obsidian-memory/SKILL.md

# Add hook to ~/.claude/hooks.json (see install.sh for format)
```

**Vault location:** `~/.claude/memory/` (override with `$CLAUDE_MEMORY_VAULT`)

See [obsidian-memory/SKILL.md](obsidian-memory/SKILL.md) for full usage docs.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- `bash`, `grep`

## License

See [LICENSE](LICENSE).
