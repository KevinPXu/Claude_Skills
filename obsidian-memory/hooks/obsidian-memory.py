#!/usr/bin/env python3
"""UserPromptSubmit / SessionStart hook: searches memory vault and injects relevant context.

On SessionStart (no prompt): injects vault config so Claude knows memory is available.
On UserPromptSubmit: extracts keywords, searches vault with BM25+graph traversal,
                     injects matching notes and write commands when relevant.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","are","was","were","be","been","being","have","has","had","do",
    "does","did","will","would","could","should","may","might","can",
    "this","that","these","those","it","its","i","you","he","she","we",
    "they","what","how","when","where","why","who","which","not","so",
    "if","then","just","also","up","out","about","some","from","there",
    "me","my","your","his","her","our","its","their","all","any","more",
    "get","set","use","new","add","one","two","make","like","need","want",
}

SAVE_THRESHOLD = 5

EXIT_SIGNALS = frozenset({
    "/exit", "/clear", "/quit", "/compact",
    "bye", "goodbye", "i'm done", "im done", "that's all",
    "thats all", "all done", "wrap up", "wrapping up",
    "signing off", "log off",
})

# Prefer the full obsidian-memory.sh shim (supports BM25 + graph via memory_engine.py).
# Fall back to the simpler mem helper if the shim isn't found.
_CANDIDATE_MEM = [
    Path.home() / "Claude_Skills/obsidian-memory/bin/obsidian-memory.sh",
    Path.home() / ".claude/hooks/mem",
]
MEM_SCRIPT = next((p for p in _CANDIDATE_MEM if p.exists()), None)


def find_vault(cwd: str):
    """Walk up from cwd looking for .claude/memory/, fall back to ~/.claude/memory/."""
    path = Path(cwd).resolve()
    while path != path.parent:
        candidate = path / ".claude" / "memory"
        if candidate.is_dir():
            return candidate
        path = path.parent
    fallback = Path.home() / ".claude" / "memory"
    return fallback if fallback.is_dir() else None


def extract_keywords(prompt: str) -> list:
    words = re.findall(r"[a-z0-9]{3,}", prompt.lower())
    return [w for w in words if w not in STOPWORDS][:15]


def search_with_engine(vault: Path, keywords: list) -> str:
    """BM25 + graph traversal via memory_engine.py.
    Returns summaries-only block (strips full note bodies to keep injection compact)."""
    if not MEM_SCRIPT or not keywords:
        return ""
    query = " ".join(keywords[:10])
    env = {**os.environ, "CLAUDE_MEMORY_VAULT": str(vault)}
    try:
        result = subprocess.run(
            [str(MEM_SCRIPT), "context", query],
            capture_output=True, text=True, timeout=8, env=env,
        )
        out = result.stdout.strip()
        if not out or "No memory notes found" in out:
            return ""
        # Keep only the Summaries block — strip Details and full note bodies
        # to keep the injected context compact. Claude can call $MEM context
        # manually when it needs full note content.
        if "### Summaries" in out:
            summaries_start = out.index("### Summaries")
            details_start = out.find("### Details", summaries_start)
            summaries = out[summaries_start:details_start].strip() if details_start != -1 else out[summaries_start:].strip()
            # Strip the header line, keep only the bullet points
            lines = summaries.splitlines()
            bullets = [l for l in lines if l.strip().startswith("-")]
            return "\n".join(bullets) if bullets else ""
        return ""
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return ""


def naive_search(vault: Path, keywords: list) -> list:
    """Fallback: simple file scan when memory_engine is unavailable."""
    if not keywords:
        return []
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    matches = []
    for md_file in vault.rglob("*.md"):
        try:
            content = md_file.read_text(errors="ignore")
            hits = len(pattern.findall(content))
            if hits > 0:
                matches.append((hits, md_file))
        except OSError:
            continue
    matches.sort(reverse=True)
    return [f for _, f in matches[:5]]


def summarize_file(path: Path, vault: Path) -> str:
    """Return '- **rel/path**: summary' for a vault note."""
    try:
        content = path.read_text(errors="ignore")
        m = re.search(r"^summary:\s*(.+)$", content, re.MULTILINE)
        if m:
            summary = m.group(1).strip()
        else:
            summary = next(
                (l.strip()[:100] for l in content.splitlines()
                 if l.strip() and not l.startswith("---") and not l.startswith("#")),
                ""
            )
        rel = path.relative_to(vault)
        return f"- **{rel}**: {summary}" if summary else f"- **{rel}**"
    except OSError:
        return ""


def get_session_count(vault: Path) -> int:
    try:
        return int((vault / ".session-count").read_text().strip())
    except (OSError, ValueError):
        return 0


def bump_session_count(vault: Path, n: int) -> None:
    try:
        (vault / ".session-count").write_text(str(n))
    except OSError:
        pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        print(json.dumps({"continue": True}))
        return

    cwd = data.get("cwd", str(Path.home()))
    prompt = data.get("prompt", "")  # FIX: was incorrectly "user_prompt"

    vault = find_vault(cwd)
    if not vault:
        print(json.dumps({"continue": True}))
        return

    mem_path = str(MEM_SCRIPT) if MEM_SCRIPT else "~/.claude/hooks/mem"

    # SessionStart: no prompt — inject compact vault reference
    if not prompt:
        msg = f'Memory vault active. MEM={mem_path} VAULT={vault}'
        print(json.dumps({"continue": True, "systemMessage": msg}))
        return

    # Per-vault session tracking (FIX: was a single global file shared across all projects)
    count = get_session_count(vault) + 1
    bump_session_count(vault, count % 10000)

    # Exit detection — short prompts only to avoid false positives
    prompt_lower = prompt.lower().strip()
    is_exit = prompt_lower in EXIT_SIGNALS
    if is_exit and count > 1:
        msg = (
            f"--- Memory Save Reminder ---\n"
            f"The user is ending this session ({count} exchanges).\n"
            "Review the conversation for saveable decisions, insights, or context.\n"
            "Present them as a NUMBERED LIST with one-line descriptions, e.g.:\n"
            "  1. [decision] Chose PostgreSQL over DynamoDB for analytics queries\n"
            "  2. [preference] User wants terse commit messages\n"
            'Then ask: "Which would you like me to save? (reply with numbers, e.g. 1,3 or \'all\' or \'none\')"\n'
            "Only save the items the user selects. Do not exit or clear until the user responds.\n"
            "--- End Reminder ---"
        )
        print(json.dumps({"continue": True, "systemMessage": msg}))
        return

    # Extract keywords and search
    keywords = extract_keywords(prompt)
    context_output = search_with_engine(vault, keywords)

    # Fallback to naive search if memory_engine unavailable
    if not context_output and not MEM_SCRIPT and keywords:
        matched = naive_search(vault, keywords)
        summaries = [s for f in matched for s in [summarize_file(f, vault)] if s]
        if summaries:
            context_output = "\n".join(summaries)

    # Build message
    parts = []

    if context_output:
        parts.append(f"Memory notes (use $MEM context \"<query>\" for full content):\n{context_output}")

    # Periodic save reminder (FIX: was threshold 25, now 5)
    if count >= SAVE_THRESHOLD and count % SAVE_THRESHOLD == 0:
        parts.append(
            f"--- Memory Save Reminder ---\n"
            f"This session has had {count} exchanges.\n"
            "Review the conversation for saveable decisions, insights, or context.\n"
            "Present them as a NUMBERED LIST with one-line descriptions.\n"
            'Then ask: "Which would you like me to save? (reply with numbers, e.g. 1,3 or \'all\' or \'none\')"\n'
            "Only save the items the user selects.\n"
            "--- End Reminder ---"
        )

    # Config block: only at save reminders (not on every notes injection)
    # When notes are found without a save reminder, Claude uses the MEM path
    # from session start or falls back to ~/.claude/hooks/mem.
    if count >= SAVE_THRESHOLD and count % SAVE_THRESHOLD == 0:
        parts.append(
            "--- Obsidian Memory Config ---\n"
            f"MEM: {mem_path}\n"
            f'export CLAUDE_MEMORY_VAULT="{vault}"\n'
            f'Save:   CLAUDE_MEMORY_VAULT="{vault}" $MEM write "<path>" "<content>"\n'
            f'Append: CLAUDE_MEMORY_VAULT="{vault}" $MEM append "<path>" "<content>"\n'
            f'Link:   CLAUDE_MEMORY_VAULT="{vault}" $MEM link "<from>" "<to>"\n'
            "One decision per note. Link related decisions with [[wikilinks]]. Add summary: to frontmatter.\n"
            "Ask user before saving. Never run $MEM init.\n"
            "--- End Config ---"
        )

    if not parts:
        print(json.dumps({"continue": True}))
        return

    print(json.dumps({"continue": True, "systemMessage": "\n\n".join(parts)}))


if __name__ == "__main__":
    main()
