#!/usr/bin/env python3
"""
memory_engine.py — SQLite-backed graph engine for obsidian-memory.

Markdown files remain the source of truth. SQLite (.index.db) is a
disposable read-optimized cache with FTS5 search and a bidirectional
link graph. Delete .index.db anytime — it rebuilds from the .md files.

Usage: memory_engine.py <command> [args...]
       (same interface as obsidian-memory.sh)
"""

import os
import re
import sqlite3
import sys
from pathlib import Path

# --- Config ---

VAULT_DIR = Path(
    os.environ.get("CLAUDE_MEMORY_VAULT", os.path.expanduser("~/.claude/memory"))
)
DB_NAME = ".index.db"
MAX_CONTEXT_LINES = 200
MAX_NOTE_LINES = 30
HUB_NOTES = frozenset(
    {"Index.md", "Projects.md", "Patterns.md", "Tools.md", "People.md", "Preferences.md"}
)

# BM25 column weights: path, title, summary, content
BM25_WEIGHTS = (1.0, 5.0, 3.0, 1.0)

# Graph traversal decay factors
FORWARD_DECAY = 0.5
BACKLINK_DECAY = 0.4

# Module-level FTS5 availability flag (set by get_db)
_has_fts5 = False


# --- Frontmatter & link parsing ---


def parse_frontmatter(text):
    """Extract YAML-ish frontmatter. Returns (metadata_dict, body_text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip()
    body = text[end + 4 :].strip()

    meta = {}
    for line in fm.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                val = val[1:-1]
            meta[key] = val
    return meta, body


def extract_wikilinks(text):
    """Return deduplicated list of [[wikilink]] target names."""
    raw = re.findall(r"\[\[([^\]]+)\]\]", text)
    seen = set()
    result = []
    for link in raw:
        name = link.split("|")[0].strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def is_hub_note(rel_path):
    return Path(rel_path).name in HUB_NOTES


def ensure_vault():
    if not VAULT_DIR.is_dir():
        print(f"ERROR: Memory vault not found at {VAULT_DIR}", file=sys.stderr)
        print("Run 'obsidian-memory.sh init' to create it.", file=sys.stderr)
        sys.exit(1)


# --- Database ---

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    path TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    mtime REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS links (
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    PRIMARY KEY (source, target)
);

CREATE INDEX IF NOT EXISTS idx_links_target ON links(target);
"""

SCHEMA_FTS5 = """
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    path, title, summary, content,
    tokenize='porter unicode61'
);
"""


def get_db():
    """Open (or create) the SQLite index. Returns a connection."""
    global _has_fts5
    db_path = VAULT_DIR / DB_NAME
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)

    try:
        conn.executescript(SCHEMA_FTS5)
        _has_fts5 = True
    except sqlite3.OperationalError:
        _has_fts5 = False

    return conn


# --- Index sync ---


def resolve_link_from_db(name, conn):
    """Resolve a wikilink name to a note path using the index."""
    cur = conn.execute(
        "SELECT path FROM notes WHERE path LIKE ? OR path = ?",
        (f"%/{name}.md", f"{name}.md"),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "SELECT path FROM notes WHERE LOWER(path) LIKE LOWER(?) OR LOWER(path) = LOWER(?)",
        (f"%/{name}.md", f"{name}.md"),
    )
    row = cur.fetchone()
    return row[0] if row else None


def sync_index(conn):
    """Sync SQLite index with markdown files on disk (two-pass: notes, then links)."""
    if not VAULT_DIR.is_dir():
        return

    # Discover .md files on disk
    disk_files = {}
    for md in VAULT_DIR.rglob("*.md"):
        rel = str(md.relative_to(VAULT_DIR))
        if rel.startswith("."):
            continue
        disk_files[rel] = md.stat().st_mtime

    # Current indexed state
    indexed = {}
    for row in conn.execute("SELECT path, mtime FROM notes"):
        indexed[row[0]] = row[1]

    # --- Pass 1: upsert notes, remove deleted ---
    removed = set(indexed) - set(disk_files)
    for path in removed:
        conn.execute("DELETE FROM notes WHERE path = ?", (path,))
        if _has_fts5:
            conn.execute("DELETE FROM notes_fts WHERE path = ?", (path,))
        conn.execute("DELETE FROM links WHERE source = ? OR target = ?", (path, path))

    changed = []
    for rel_path, mtime in disk_files.items():
        if rel_path in indexed and abs(indexed[rel_path] - mtime) < 0.001:
            continue

        full_path = VAULT_DIR / rel_path
        try:
            content = full_path.read_text(errors="replace")
        except OSError:
            continue

        meta, body = parse_frontmatter(content)
        title = meta.get("title", Path(rel_path).stem)
        summary = meta.get("summary", "")
        tags = meta.get("tags", "")

        conn.execute(
            "INSERT OR REPLACE INTO notes (path, title, summary, tags, content, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rel_path, title, summary, tags, content, mtime),
        )

        if _has_fts5:
            conn.execute("DELETE FROM notes_fts WHERE path = ?", (rel_path,))
            conn.execute(
                "INSERT INTO notes_fts (path, title, summary, content) VALUES (?, ?, ?, ?)",
                (rel_path, title, summary, body),
            )

        changed.append((rel_path, content))

    # --- Pass 2: rebuild links for changed notes ---
    for rel_path, content in changed:
        conn.execute("DELETE FROM links WHERE source = ?", (rel_path,))
        for link_name in extract_wikilinks(content):
            target = resolve_link_from_db(link_name, conn)
            if target and target != rel_path:
                conn.execute(
                    "INSERT OR IGNORE INTO links (source, target) VALUES (?, ?)",
                    (rel_path, target),
                )

    conn.commit()


# --- Search ---


def escape_fts_query(query):
    """Quote each word for FTS5 MATCH (literal matching, no operators)."""
    words = query.split()
    return " ".join(f'"{w}"' for w in words if w.strip())


def search_bm25(conn, query, limit=10):
    """FTS5 BM25-ranked search. Returns [(path, score), ...]."""
    if not _has_fts5:
        return search_fallback(conn, query, limit)

    fts_query = escape_fts_query(query)
    if not fts_query:
        return []

    try:
        rows = conn.execute(
            "SELECT path, bm25(notes_fts, ?, ?, ?, ?) AS score "
            "FROM notes_fts WHERE notes_fts MATCH ? ORDER BY score LIMIT ?",
            (*BM25_WEIGHTS, fts_query, limit),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except sqlite3.OperationalError:
        return search_fallback(conn, query, limit)


def search_fallback(conn, query, limit=10):
    """LIKE-based fallback when FTS5 is unavailable."""
    words = query.lower().split()
    if not words:
        return []

    scores = {}
    for word in words:
        pattern = f"%{word}%"
        rows = conn.execute(
            "SELECT path, title FROM notes "
            "WHERE LOWER(content) LIKE ? OR LOWER(title) LIKE ?",
            (pattern, pattern),
        ).fetchall()
        for path, title in rows:
            scores[path] = scores.get(path, 0) + 1
            if word in title.lower():
                scores[path] += 3

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:limit]
    return [(path, -score) for path, score in ranked]


# --- Graph traversal ---


def get_forward_links(conn, path):
    return [r[0] for r in conn.execute(
        "SELECT target FROM links WHERE source = ?", (path,)
    ).fetchall()]


def get_backlinks(conn, path):
    return [r[0] for r in conn.execute(
        "SELECT source FROM links WHERE target = ?", (path,)
    ).fetchall()]


def build_context_graph(conn, seeds):
    """
    Bidirectional expansion with convergence scoring.

    Seeds get normalized BM25 scores. Forward links get seed_score * 0.5,
    backlinks get seed_score * 0.4. Notes reachable from multiple seeds
    accumulate score additively — this is the convergence signal that
    identifies tight clusters.
    """
    scores = {}

    if not seeds:
        return scores

    max_bm25 = max(abs(s) for _, s in seeds) or 1.0
    for path, bm25_score in seeds:
        scores[path] = abs(bm25_score) / max_bm25

    for seed_path, _ in seeds:
        seed_score = scores[seed_path]

        for target in get_forward_links(conn, seed_path):
            if not is_hub_note(target):
                scores[target] = scores.get(target, 0) + seed_score * FORWARD_DECAY

        for source in get_backlinks(conn, seed_path):
            if not is_hub_note(source):
                scores[source] = scores.get(source, 0) + seed_score * BACKLINK_DECAY

    return scores


# --- Commands ---


def cmd_search(query, max_results="10"):
    max_results = int(max_results)
    ensure_vault()
    conn = get_db()
    sync_index(conn)
    for path, _ in search_bm25(conn, query, max_results):
        print(path)


def cmd_read(path):
    ensure_vault()
    full = VAULT_DIR / path
    if not full.is_file():
        print(f"ERROR: Note not found: {path}", file=sys.stderr)
        sys.exit(1)
    print(full.read_text(errors="replace"))


def cmd_write(path, content):
    ensure_vault()
    full = VAULT_DIR / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content + "\n")

    line_count = content.count("\n") + 1
    if line_count > MAX_NOTE_LINES:
        print(
            f"WARNING: Note '{path}' is {line_count} lines (>{MAX_NOTE_LINES}).",
            file=sys.stderr,
        )
        print(
            "Consider splitting into smaller atomic notes linked with [[wikilinks]].",
            file=sys.stderr,
        )


def cmd_append(path, content):
    ensure_vault()
    full = VAULT_DIR / path
    if not full.is_file():
        print(f"ERROR: Note not found: {path} (use 'write' to create)", file=sys.stderr)
        sys.exit(1)
    with open(full, "a") as f:
        f.write("\n" + content + "\n")


def cmd_list(folder="."):
    ensure_vault()
    full = VAULT_DIR / folder
    if not full.is_dir():
        print(f"ERROR: Folder not found: {folder}", file=sys.stderr)
        sys.exit(1)
    for md in sorted(full.glob("*.md")):
        print(md.name)


def cmd_link(from_path, to_path):
    ensure_vault()
    full = VAULT_DIR / from_path
    if not full.is_file():
        print(f"ERROR: Note not found: {from_path}", file=sys.stderr)
        sys.exit(1)

    link_name = Path(to_path).stem
    existing = full.read_text(errors="replace")
    if f"[[{link_name}]]" in existing:
        return

    with open(full, "a") as f:
        f.write(f"\n- [[{link_name}]]\n")


def cmd_index():
    ensure_vault()
    idx = VAULT_DIR / "Index.md"
    if not idx.is_file():
        print("ERROR: No Index.md found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)
    print(idx.read_text(errors="replace"))


def cmd_context(query, max_seeds="5"):
    """BM25 search + bidirectional graph expansion + budget-aware output."""
    max_seeds = int(max_seeds)
    ensure_vault()
    conn = get_db()
    sync_index(conn)

    seeds = search_bm25(conn, query, max_seeds)
    if not seeds:
        print(f"No memory notes found for: {query}")
        return

    scores = build_context_graph(conn, seeds)
    scores = {p: s for p, s in scores.items() if not is_hub_note(p)}

    if not scores:
        print(f"No memory notes found for: {query}")
        return

    seed_paths = {p for p, _ in seeds}
    ranked = sorted(scores.items(), key=lambda x: -x[1])

    total_lines = 0
    print(f"--- Memory Context for: {query} ---")

    for path, score in ranked:
        if total_lines >= MAX_CONTEXT_LINES:
            break

        full = VAULT_DIR / path
        if not full.is_file():
            continue

        content = full.read_text(errors="replace")
        lines = content.split("\n")
        note_lines = len(lines)
        is_seed = path in seed_paths

        if is_seed:
            if total_lines + note_lines > MAX_CONTEXT_LINES:
                remaining = MAX_CONTEXT_LINES - total_lines
                if remaining > 5:
                    print(f"\n## {Path(path).stem} [from: {path}]")
                    print("\n".join(lines[:remaining]))
                    print("... (truncated)")
                    total_lines += remaining + 2
                break
            print(f"\n## {Path(path).stem} [from: {path}]")
            print(content)
            total_lines += note_lines + 2
        else:
            meta, _ = parse_frontmatter(content)
            summary = meta.get("summary", "")

            if summary:
                print(f"\n## {Path(path).stem} [linked, from: {path}]")
                print(summary)
                total_lines += 3
            else:
                excerpt_lines = min(10, note_lines)
                if total_lines + excerpt_lines <= MAX_CONTEXT_LINES:
                    print(f"\n## {Path(path).stem} [linked, from: {path}]")
                    print("\n".join(lines[:excerpt_lines]))
                    if note_lines > excerpt_lines:
                        print(f'... (use $MEM read "{path}" for full note)')
                    total_lines += excerpt_lines + 2

    print("\n--- End Memory Context ---")


def cmd_related(path, depth="1"):
    depth = int(depth)
    ensure_vault()
    full = VAULT_DIR / path
    if not full.is_file():
        print(f"ERROR: Note not found: {path}", file=sys.stderr)
        sys.exit(1)

    conn = get_db()
    sync_index(conn)

    visited = {path}
    current_level = [path]

    for _ in range(depth):
        next_level = []
        for note in current_level:
            for target in get_forward_links(conn, note):
                if target not in visited:
                    visited.add(target)
                    next_level.append(target)
                    print(target)
        current_level = next_level
        if not current_level:
            break


def cmd_tags(tag):
    ensure_vault()
    conn = get_db()
    sync_index(conn)
    rows = conn.execute(
        "SELECT path FROM notes WHERE tags LIKE ? ORDER BY path",
        (f"%{tag}%",),
    ).fetchall()
    for (path,) in rows:
        print(path)


def cmd_init():
    print(f"Initializing memory vault at {VAULT_DIR}...")
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    (VAULT_DIR / ".obsidian").mkdir(exist_ok=True)

    (VAULT_DIR / "Index.md").write_text(
        "---\ntags: [claude-memory, index]\naliases: [Memory Index]\n---\n"
        "# Claude Memory Index\n\n"
        "Central hub for Claude's persistent memory graph.\n\n"
        "## Categories\n"
        "- [[Preferences]] — User preferences, workflow, tools, style\n"
        "- [[Projects]] — Per-project notes and decisions\n"
        "- [[Patterns]] — Reusable coding patterns and debugging insights\n"
        "- [[Tools]] — Tool and framework knowledge\n"
        "- [[People]] — People and contacts\n\n"
        "## Recent\n"
        "<!-- Auto-updated with recently modified memory notes -->\n"
    )
    print("  Created Index.md")

    (VAULT_DIR / "Preferences.md").write_text(
        "---\ntags: [claude-memory, preferences]\n---\n"
        "# User Preferences\n\n"
        "## Workflow\n\n## Communication Style\n\n## Tools\n\n"
        "## Links\n- [[Index]]\n"
    )
    print("  Created Preferences.md")

    for cat in ("Projects", "Patterns", "Tools", "People"):
        (VAULT_DIR / cat).mkdir(exist_ok=True)
        (VAULT_DIR / f"{cat}.md").write_text(
            f"---\ntags: [claude-memory, category]\n---\n"
            f"# {cat}\n\n"
            f"## Notes\n<!-- Links to {cat.lower()} notes will be added here -->\n\n"
            f"## Links\n- [[Index]]\n"
        )
        print(f"  Created {cat}.md")

    conn = get_db()
    sync_index(conn)
    conn.close()

    print(f"\nMemory vault initialized at: {VAULT_DIR}")
    print("\nStructure:")
    print("  Index.md          (hub)")
    print("  Preferences.md    (user prefs)")
    for cat in ("Projects", "Patterns", "Tools", "People"):
        print(f"  {cat}/            ({cat.lower()} notes)")
        print(f"  {cat}.md          ({cat.lower()} index)")
    print("  .obsidian/        (open in Obsidian for graph view)")
    print("  .index.db         (SQLite cache — auto-rebuilt, safe to delete)")


def cmd_info():
    if not VAULT_DIR.is_dir():
        print(f"Memory vault not found at {VAULT_DIR}")
        return

    conn = get_db()
    sync_index(conn)

    note_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    fts = "FTS5 (BM25)" if _has_fts5 else "fallback (LIKE)"

    total = sum(f.stat().st_size for f in VAULT_DIR.rglob("*") if f.is_file())
    size = f"{total}B" if total < 1024 else f"{total/1024:.0f}K" if total < 1048576 else f"{total/1048576:.1f}M"

    print(f"Memory Vault: {VAULT_DIR}")
    print(f"Notes:        {note_count}")
    print(f"Links:        {link_count}")
    print(f"Size:         {size}")
    print(f"Search:       {fts}")
    print(f"Index:        {VAULT_DIR / DB_NAME}")


def cmd_rebuild():
    """Force-rebuild the SQLite index from markdown files."""
    ensure_vault()
    db_path = VAULT_DIR / DB_NAME
    if db_path.exists():
        db_path.unlink()
    conn = get_db()
    sync_index(conn)

    note_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    print(f"Rebuilt index: {note_count} notes, {link_count} links")
    conn.close()


# --- Main ---

COMMANDS = {
    "search": lambda args: cmd_search(args[0], *args[1:2]),
    "read": lambda args: cmd_read(args[0]),
    "write": lambda args: cmd_write(args[0], args[1]),
    "append": lambda args: cmd_append(args[0], args[1]),
    "list": lambda args: cmd_list(*args[:1]),
    "link": lambda args: cmd_link(args[0], args[1]),
    "index": lambda args: cmd_index(),
    "context": lambda args: cmd_context(args[0], *args[1:2]),
    "related": lambda args: cmd_related(args[0], *args[1:2]),
    "tags": lambda args: cmd_tags(args[0]),
    "init": lambda args: cmd_init(),
    "info": lambda args: cmd_info(),
    "rebuild": lambda args: cmd_rebuild(),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        print("Usage: memory_engine.py <command> [args...]")
        print()
        print("SQLite-backed memory graph for Claude. Markdown files are the source of truth.")
        print(f"Vault: $CLAUDE_MEMORY_VAULT (current: {VAULT_DIR})")
        print()
        print("Commands:")
        print("  search <query> [max]    Search notes (BM25 ranked via FTS5)")
        print("  read <path>             Read a note")
        print("  write <path> <content>  Write/overwrite a note")
        print("  append <path> <content> Append to an existing note")
        print("  list [folder]           List notes in a folder")
        print("  link <from> <to>        Add a [[wikilink]] between notes")
        print("  index                   Read the memory index")
        print("  context <query> [max]   Smart context: BM25 + graph expansion")
        print("  related <path> [depth]  Follow links from a note (BFS)")
        print("  tags <tag>              Find notes with a given tag")
        print("  init                    Initialize the memory vault")
        print("  info                    Show vault stats")
        print("  rebuild                 Force rebuild the SQLite index")
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print("Run 'memory_engine.py help' for usage.", file=sys.stderr)
        sys.exit(1)

    try:
        COMMANDS[cmd](args)
    except (IndexError, TypeError):
        print(f"ERROR: Wrong number of arguments for '{cmd}'", file=sys.stderr)
        print("Run 'memory_engine.py help' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
