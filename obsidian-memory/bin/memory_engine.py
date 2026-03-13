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
from datetime import datetime, timezone
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

# Staleness: notes lose this fraction of their score per day since last update.
# At 0.005, a 30-day-old note keeps ~86% of its score; 180-day keeps ~41%.
STALENESS_DECAY_PER_DAY = 0.005

# PPR parameters
PPR_ALPHA = 0.3       # restart probability (higher = tighter clusters)
PPR_ITERATIONS = 10   # convergence iterations
PPR_TOP_K = 10        # candidates to consider before Steiner pruning

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


def _now_iso():
    """Return current UTC date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_timestamps(content):
    """
    Add 'created' and 'updated' to frontmatter if missing; always refresh 'updated'.
    Creates frontmatter block if the note doesn't have one.
    Returns the updated content string.
    """
    today = _now_iso()

    if not content.startswith("---"):
        # No frontmatter — wrap content with one
        return f"---\ncreated: {today}\nupdated: {today}\n---\n{content}"

    end = content.find("\n---", 3)
    if end == -1:
        return content

    fm_block = content[3:end]
    body = content[end + 4:]

    # Parse existing lines, preserving order
    fm_lines = fm_block.strip().split("\n")
    has_created = False
    has_updated = False
    new_lines = []

    for line in fm_lines:
        key = line.partition(":")[0].strip()
        if key == "created":
            has_created = True
            new_lines.append(line)
        elif key == "updated":
            has_updated = True
            new_lines.append(f"updated: {today}")
        else:
            new_lines.append(line)

    if not has_created:
        new_lines.append(f"created: {today}")
    if not has_updated:
        new_lines.append(f"updated: {today}")

    return f"---\n" + "\n".join(new_lines) + f"\n---\n{body}"


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
    """Build FTS5 MATCH query with OR logic and prefix matching.

    Each keyword gets a prefix wildcard (deploy -> deploy*) so
    morphological variants match even when porter stemming falls
    short (e.g., "deployment" doesn't stem to "deploy" in SQLite's
    porter). OR matching ensures partial keyword overlap still finds
    notes — BM25 naturally ranks notes with more matches higher.

    Special FTS5 operator characters are stripped to prevent
    syntax errors.
    """
    # Strip FTS5 operators that could cause syntax errors
    cleaned = re.sub(r'["*^{}()\[\]:!]', " ", query)
    words = [w for w in cleaned.split() if w.strip() and w not in ("OR", "AND", "NOT", "NEAR")]
    if not words:
        return ""
    # Use prefix matching for each word to catch morphological variants
    prefixed = [f"{w}*" for w in words]
    if len(prefixed) == 1:
        return prefixed[0]
    return " OR ".join(prefixed)


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
        results = [(r[0], r[1]) for r in rows]
        # Fall back to LIKE search when FTS5 returns nothing — catches
        # morphological variants that prefix matching misses (e.g.,
        # "deployment" query matching "Deploy" in content).
        if not results:
            return search_fallback(conn, query, limit)
        return results
    except sqlite3.OperationalError:
        return search_fallback(conn, query, limit)


def _extract_roots(words):
    """Extract candidate search roots from words.

    Strips common English suffixes to catch morphological variants
    where "deployment" should match "deploy". Returns deduplicated
    list of original words plus their roots (min 4 chars).
    """
    suffixes = ("ment", "tion", "sion", "ness", "ment", "ance", "ence",
                "able", "ible", "ated", "ting", "ing", "ful", "ous",
                "ive", "ize", "ise", "ify", "ity", "ally", "ly", "ed",
                "er", "est", "ure")
    roots = set(words)
    for word in words:
        for suffix in suffixes:
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                roots.add(word[:-len(suffix)])
                break
    return list(roots)


def search_fallback(conn, query, limit=10):
    """LIKE-based fallback when FTS5 is unavailable or returns nothing.

    Uses substring matching (%word%) so it catches morphological
    variants that FTS5 prefix matching misses. Only considers words
    with 4+ characters to avoid noise from short substrings.
    Strips common suffixes to find word roots (e.g., "deployment" -> "deploy").
    """
    words = [w for w in query.lower().split() if len(w) >= 4]
    if not words:
        return []

    # Include root forms so "deployment" also searches for "deploy"
    search_terms = _extract_roots(words)

    scores = {}
    for word in search_terms:
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


def get_neighbors(conn, path):
    """Get all neighbors (forward links + backlinks), excluding hubs."""
    forward = [r[0] for r in conn.execute(
        "SELECT target FROM links WHERE source = ?", (path,)
    ).fetchall()]
    backward = [r[0] for r in conn.execute(
        "SELECT source FROM links WHERE target = ?", (path,)
    ).fetchall()]
    return [n for n in set(forward + backward) if not is_hub_note(n)]


def personalized_pagerank(conn, seeds):
    """
    Personalized PageRank with restart on seed nodes.

    Walks the bidirectional link graph, teleporting back to seeds with
    probability alpha. Degree normalization is built in — hubs spread
    their score thinly across many edges, so they naturally rank lower.

    On tiny graphs (<=2 non-hub nodes), skips iteration and returns
    normalized seed scores directly — PPR adds no value when there's
    nothing to explore.
    """
    if not seeds:
        return {}

    # Normalize BM25 scores to a probability distribution over seeds
    max_bm25 = max(abs(s) for _, s in seeds) or 1.0
    seed_scores = {}
    total = 0.0
    for path, bm25_score in seeds:
        s = abs(bm25_score) / max_bm25
        seed_scores[path] = s
        total += s
    if total > 0:
        seed_scores = {p: s / total for p, s in seed_scores.items()}

    # Skip iteration if there are no links to walk
    link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    if link_count == 0:
        return dict(seed_scores)

    # Initialize scores at seed distribution
    scores = dict(seed_scores)

    # Pre-fetch neighbor lists for all nodes we might visit
    # (avoids repeated SQL queries during iteration)
    neighbor_cache = {}

    for _ in range(PPR_ITERATIONS):
        new_scores = {}

        # Restart component: teleport back to seeds
        for path, s in seed_scores.items():
            new_scores[path] = new_scores.get(path, 0.0) + PPR_ALPHA * s

        # Walk component: spread (1-alpha) of each node's score to neighbors
        for node, score in scores.items():
            if score < 1e-6:
                continue

            if node not in neighbor_cache:
                neighbor_cache[node] = get_neighbors(conn, node)
            neighbors = neighbor_cache[node]

            if not neighbors:
                # Dead end — return score to seeds (absorbing)
                for path, s in seed_scores.items():
                    new_scores[path] = new_scores.get(path, 0.0) + (1 - PPR_ALPHA) * score * s
                continue

            share = (1 - PPR_ALPHA) * score / len(neighbors)
            for neighbor in neighbors:
                new_scores[neighbor] = new_scores.get(neighbor, 0.0) + share

        scores = new_scores

    return scores


def steiner_tree(conn, seed_paths, candidates):
    """
    Approximate Steiner tree: find minimum connecting subgraph through candidates.

    Given seed nodes and PPR-scored candidates, find the notes that sit on
    shortest paths between seeds. These connecting nodes are the most
    valuable context — they explain how seeds relate to each other.

    Uses BFS from each seed restricted to the candidate set. Returns the
    set of nodes on the tree (seeds + connectors).

    On small inputs (0-1 seeds, or no candidates beyond seeds), returns
    seeds directly — there's nothing to connect.
    """
    seeds = list(seed_paths)
    if len(seeds) <= 1:
        return set(seeds)

    # Build adjacency restricted to candidates + seeds
    node_set = set(candidates) | set(seeds)
    adj = {}
    for node in node_set:
        neighbors = get_neighbors(conn, node)
        adj[node] = [n for n in neighbors if n in node_set]

    # BFS from a node within the restricted graph, return parent map
    def bfs(start):
        visited = {start: None}
        queue = [start]
        qi = 0
        while qi < len(queue):
            current = queue[qi]
            qi += 1
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited[neighbor] = current
                    queue.append(neighbor)
        return visited

    # Greedily connect seeds: start with first seed, connect nearest unconnected seed
    tree_nodes = {seeds[0]}
    connected = {seeds[0]}
    remaining = set(seeds[1:])

    while remaining:
        best_path = None
        best_target = None
        best_len = float("inf")

        # BFS from each connected node to find nearest remaining seed
        # For efficiency, do one BFS from each tree node and cache
        for tree_node in list(connected):
            parents = bfs(tree_node)
            for target in remaining:
                if target in parents:
                    # Reconstruct path
                    path = []
                    current = target
                    while current is not None:
                        path.append(current)
                        current = parents[current]
                    if len(path) < best_len:
                        best_len = len(path)
                        best_path = path
                        best_target = target

        if best_path is None:
            # Remaining seeds unreachable — add them directly
            tree_nodes.update(remaining)
            break

        tree_nodes.update(best_path)
        connected.update(best_path)
        remaining.discard(best_target)

    return tree_nodes


def build_context_graph(conn, seeds):
    """
    PPR + Steiner hybrid for context selection.

    1. Personalized PageRank from seeds — finds the cluster of related notes
       with degree-normalized scoring (hubs dampened automatically)
    2. Take top-K PPR candidates
    3. Steiner tree through those candidates — prunes to the minimum subgraph
       that connects seeds, keeping only essential linking notes
    4. Return scores for tree nodes only

    On small graphs this gracefully degrades: PPR returns just the seeds,
    Steiner returns them as-is. Zero overhead until the graph is big enough
    to benefit from pruning.
    """
    if not seeds:
        return {}

    # Step 1: PPR
    ppr_scores = personalized_pagerank(conn, seeds)

    # Filter out hub notes
    ppr_scores = {p: s for p, s in ppr_scores.items() if not is_hub_note(p)}

    if not ppr_scores:
        return {}

    # Step 2: Top-K candidates
    ranked = sorted(ppr_scores.items(), key=lambda x: -x[1])
    top_k = ranked[:PPR_TOP_K]
    candidate_paths = [p for p, _ in top_k]

    # Step 3: Steiner tree to prune
    seed_paths = {p for p, _ in seeds}
    tree_nodes = steiner_tree(conn, seed_paths, candidate_paths)

    # Step 4: Return only tree nodes with their PPR scores
    return {p: ppr_scores.get(p, 0.0) for p in tree_nodes if p in ppr_scores}


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
    content = ensure_timestamps(content)
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
    # Update the 'updated' timestamp in frontmatter
    existing = full.read_text(errors="replace")
    existing = ensure_timestamps(existing)
    full.write_text(existing.rstrip("\n") + "\n" + content + "\n")


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
    """
    Summary-first context loading.

    Two-pass approach to maximize relevance within the line budget:
      Pass 1 — Print a compact summary line for every matched note (cheap).
      Pass 2 — Expand the highest-scoring notes with full content using
               whatever budget remains after summaries.

    This ensures the caller always sees *all* relevant topics (pass 1) and
    gets deep detail on the most important ones (pass 2), rather than
    blowing the budget on the first large note.
    """
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

    # Apply staleness decay: reduce scores for notes not recently updated
    today = datetime.now(timezone.utc)
    note_cache = {}  # path -> (meta, body, full_content, line_count)
    for path in list(scores):
        full = VAULT_DIR / path
        if not full.is_file():
            scores.pop(path, None)
            continue
        content = full.read_text(errors="replace")
        meta, body = parse_frontmatter(content)
        note_cache[path] = (meta, body, content, len(content.split("\n")))

        updated = meta.get("updated", "")
        if updated:
            try:
                updated_date = datetime.strptime(updated, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                days_old = (today - updated_date).days
                decay = max(0.1, 1.0 - STALENESS_DECAY_PER_DAY * days_old)
                scores[path] *= decay
            except ValueError:
                pass  # malformed date, skip decay

    ranked = sorted(scores.items(), key=lambda x: -x[1])

    total_lines = 0
    print(f"--- Memory Context for: {query} ---")

    # --- Pass 1: summaries for all notes ---
    print("\n### Summaries\n")
    total_lines += 3
    for path, _score in ranked:
        if path not in note_cache:
            continue
        if total_lines >= MAX_CONTEXT_LINES:
            break
        meta, body, _content, _lc = note_cache[path]
        summary = meta.get("summary", "")
        if not summary:
            # Fall back to first non-empty body line as summary
            for line in body.split("\n"):
                stripped = line.strip().lstrip("# ").strip()
                if stripped:
                    summary = stripped[:120]
                    break
        if not summary:
            summary = "(no summary)"
        print(f"- **{Path(path).stem}** ({path}): {summary}")
        total_lines += 1

    # --- Pass 2: expand top notes with full content ---
    if total_lines < MAX_CONTEXT_LINES:
        print("\n### Details\n")
        total_lines += 3
        for path, _score in ranked:
            if path not in note_cache:
                continue
            if total_lines >= MAX_CONTEXT_LINES:
                break
            _meta, _body, content, note_lines = note_cache[path]
            remaining = MAX_CONTEXT_LINES - total_lines
            if remaining < 5:
                break
            print(f"\n## {Path(path).stem} [from: {path}]")
            total_lines += 2
            lines = content.split("\n")
            if note_lines <= remaining:
                print(content)
                total_lines += note_lines
            else:
                print("\n".join(lines[:remaining]))
                print("... (truncated)")
                total_lines += remaining + 1

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
            for target in get_neighbors(conn, note):
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


def cmd_prune(before_date, confirm=""):
    """
    List (or delete) notes not updated since a given date.

    Usage:
      prune 2026-01-01            # list candidates
      prune 2026-01-01 --confirm  # actually delete them
    """
    ensure_vault()
    try:
        cutoff = datetime.strptime(before_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"ERROR: Invalid date format '{before_date}'. Use YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    do_delete = confirm == "--confirm"
    candidates = []

    for md in sorted(VAULT_DIR.rglob("*.md")):
        rel = str(md.relative_to(VAULT_DIR))
        if rel.startswith(".") or is_hub_note(rel):
            continue

        content = md.read_text(errors="replace")
        meta, _ = parse_frontmatter(content)
        updated = meta.get("updated", meta.get("created", ""))

        if not updated:
            # No timestamp — use file mtime as fallback
            mtime = datetime.fromtimestamp(md.stat().st_mtime, tz=timezone.utc)
            updated_date = mtime
            updated = mtime.strftime("%Y-%m-%d") + " (from mtime)"
        else:
            try:
                updated_date = datetime.strptime(updated, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue

        if updated_date < cutoff:
            candidates.append((rel, updated))

    if not candidates:
        print(f"No notes found with updates before {before_date}.")
        return

    if do_delete:
        for rel, updated in candidates:
            full = VAULT_DIR / rel
            full.unlink()
            print(f"  DELETED: {rel} (last updated: {updated})")
        print(f"\nPruned {len(candidates)} note(s).")
        # Rebuild index after deletions
        conn = get_db()
        sync_index(conn)
        conn.close()
    else:
        print(f"Notes not updated since {before_date}:\n")
        for rel, updated in candidates:
            print(f"  {rel}  (last updated: {updated})")
        print(f"\n{len(candidates)} note(s) found.")
        print(f"Run with --confirm to delete: prune {before_date} --confirm")


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
    "prune": lambda args: cmd_prune(args[0], *args[1:2]),
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
        print("  prune <date> [--confirm] List/delete notes not updated since date")
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
