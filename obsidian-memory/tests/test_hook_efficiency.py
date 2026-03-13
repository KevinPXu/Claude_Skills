#!/usr/bin/env python3
"""
Hook efficiency benchmarks for obsidian-memory.

Tests the context-loader.sh hook for:
  - False-positive context injection (irrelevant notes for unrelated prompts)
  - Context size overhead (chars injected per prompt)
  - Keyword extraction quality
  - Config block overhead
  - Execution time
  - Session counter behavior
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(ENGINE_DIR))

import memory_engine as engine

HOOK_PATH = Path(__file__).resolve().parent.parent / "hooks" / "context-loader.sh"
SCRIPT_PATH = ENGINE_DIR / "obsidian-memory.sh"

PASS_COUNT = 0
FAIL_COUNT = 0
TEST_VAULT = None


def setup_vault_with_notes():
    """Create a vault with realistic mixed-topic notes."""
    global TEST_VAULT
    TEST_VAULT = Path(tempfile.mkdtemp(prefix="mem_efficiency_"))
    engine.VAULT_DIR = TEST_VAULT
    os.environ["CLAUDE_MEMORY_VAULT"] = str(TEST_VAULT)

    # Auth-related notes
    (TEST_VAULT / "Projects").mkdir(parents=True)
    (TEST_VAULT / "Patterns").mkdir(parents=True)

    (TEST_VAULT / "Index.md").write_text(
        "---\ntags: [index]\n---\n# Index\n- [[Projects]]\n- [[Patterns]]\n"
    )
    (TEST_VAULT / "Projects.md").write_text(
        "---\ntags: [category]\n---\n# Projects\n- [[auth-decision]]\n- [[deploy-setup]]\n"
    )
    (TEST_VAULT / "Patterns.md").write_text(
        "---\ntags: [category]\n---\n# Patterns\n- [[error-handling]]\n"
    )
    (TEST_VAULT / "Preferences.md").write_text(
        "---\ntags: [preferences]\n---\n# Preferences\n## Workflow\n- Prefers TDD\n"
    )
    (TEST_VAULT / "Tools.md").write_text(
        "---\ntags: [category]\n---\n# Tools\n"
    )
    (TEST_VAULT / "People.md").write_text(
        "---\ntags: [category]\n---\n# People\n"
    )

    (TEST_VAULT / "Projects" / "auth-decision.md").write_text(
        "---\ntags: [claude-memory, project]\nsummary: Chose JWT over session cookies for SPA\n"
        "created: 2026-03-10\nupdated: 2026-03-10\n---\n"
        "# Auth Decision\nChose JWT. Reason: SPA with no SSR.\n## Links\n- [[token-storage]]\n"
    )
    (TEST_VAULT / "Projects" / "token-storage.md").write_text(
        "---\ntags: [claude-memory, project]\nsummary: Tokens stored in httpOnly cookies\n"
        "created: 2026-03-10\nupdated: 2026-03-10\n---\n"
        "# Token Storage\nhttpOnly cookies for XSS protection.\n## Links\n- [[auth-decision]]\n"
    )
    (TEST_VAULT / "Projects" / "deploy-setup.md").write_text(
        "---\ntags: [claude-memory, project]\nsummary: Docker Compose for local dev, K8s for prod\n"
        "created: 2026-03-08\nupdated: 2026-03-08\n---\n"
        "# Deploy Setup\nDocker Compose locally, K8s in prod.\n"
    )
    (TEST_VAULT / "Patterns" / "error-handling.md").write_text(
        "---\ntags: [claude-memory, pattern]\nsummary: Always use structured error types, not strings\n"
        "created: 2026-03-09\nupdated: 2026-03-09\n---\n"
        "# Error Handling Pattern\nUse typed errors, never bare strings.\n"
    )

    # Build SQLite index
    conn = engine.get_db()
    engine.sync_index(conn)
    conn.close()

    return TEST_VAULT


def teardown_vault():
    global TEST_VAULT
    if TEST_VAULT and TEST_VAULT.exists():
        shutil.rmtree(TEST_VAULT)
    TEST_VAULT = None


def run_hook(prompt, cwd=None):
    """Run context-loader.sh with a given prompt and return stdout + timing."""
    if cwd is None:
        cwd = str(TEST_VAULT)
    input_json = json.dumps({"prompt": prompt, "cwd": cwd})
    env = os.environ.copy()
    env["CLAUDE_MEMORY_VAULT"] = str(TEST_VAULT)
    env["OBSIDIAN_MEMORY_SCRIPT"] = str(SCRIPT_PATH)

    t0 = time.time()
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=input_json, capture_output=True, text=True, env=env, timeout=10
    )
    elapsed = time.time() - t0
    return result.stdout, result.stderr, result.returncode, elapsed


def assert_true(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS: {name}")
    else:
        FAIL_COUNT += 1
        msg = f"  FAIL: {name}"
        if detail:
            msg += f"\n    {detail}"
        print(msg)


def assert_lt(name, actual, threshold, unit=""):
    global PASS_COUNT, FAIL_COUNT
    if actual < threshold:
        PASS_COUNT += 1
        print(f"  PASS: {name} ({actual}{unit} < {threshold}{unit})")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name} ({actual}{unit} >= {threshold}{unit})")


# --- Tests ---


def test_false_positive_irrelevant_prompt():
    """Hook should inject minimal or no notes for unrelated coding prompts."""
    print("\n=== test_false_positive_irrelevant_prompt ===")
    setup_vault_with_notes()

    prompts = [
        "fix the login bug in the user authentication module",
        "refactor the database connection pool",
        "add unit tests for the payment service",
        "can you help me with this CSS layout issue",
    ]

    for prompt in prompts:
        stdout, _, rc, _ = run_hook(prompt)
        # Count how many full note expansions appear (## <name> [from: ...)
        note_expansions = stdout.count("[from:")
        has_irrelevant = "auth-decision" in stdout or "deploy-setup" in stdout or "error-handling" in stdout
        context_chars = len(stdout)

        assert_true(
            f"No false-positive notes for '{prompt[:40]}...'",
            not has_irrelevant or note_expansions == 0,
            f"Injected {note_expansions} notes, {context_chars} chars"
        )

    teardown_vault()


def test_minimal_prompt_overhead():
    """Short/trivial prompts should inject minimal context."""
    print("\n=== test_minimal_prompt_overhead ===")
    setup_vault_with_notes()

    trivial_prompts = ["hi", "thanks", "can you help me?", "yes", "no"]

    for prompt in trivial_prompts:
        stdout, _, rc, _ = run_hook(prompt)
        context_chars = len(stdout)
        has_notes = "### Details" in stdout and "[from:" in stdout

        assert_true(
            f"Minimal injection for '{prompt}' ({context_chars} chars)",
            not has_notes,
            f"Full note content injected for trivial prompt"
        )

    teardown_vault()


def test_relevant_prompt_finds_notes():
    """Memory-relevant prompts should find the right notes."""
    print("\n=== test_relevant_prompt_finds_notes ===")
    setup_vault_with_notes()

    stdout, _, rc, _ = run_hook("what was the auth decision we made?")
    assert_true("Auth query finds auth-decision note", "auth-decision" in stdout.lower() or "Auth Decision" in stdout)
    assert_true("Auth query finds token-storage via links", "token-storage" in stdout.lower() or "Token Storage" in stdout)
    assert_true("Auth query does NOT find deploy-setup", "deploy-setup" not in stdout.lower())

    stdout, _, rc, _ = run_hook("how is deployment configured?")
    assert_true("Deploy query finds deploy-setup", "deploy-setup" in stdout.lower() or "Deploy Setup" in stdout or "Docker" in stdout)

    teardown_vault()


def test_config_block_size():
    """Config block overhead should be reasonable and conditional."""
    print("\n=== test_config_block_size ===")
    setup_vault_with_notes()

    # Config block should NOT appear for trivial prompts with no matches
    stdout, _, rc, _ = run_hook("hi")
    has_config = "--- Obsidian Memory Config ---" in stdout
    assert_true("No config block for trivial prompt 'hi'", not has_config,
                f"Config block injected unnecessarily ({len(stdout)} chars)")

    # Config block SHOULD appear when notes are found
    stdout, _, rc, _ = run_hook("what was the auth decision?")
    has_config = "--- Obsidian Memory Config ---" in stdout
    assert_true("Config block present when notes found", has_config)

    if has_config:
        config_start = stdout.find("--- Obsidian Memory Config ---")
        config_end = stdout.find("--- End Config ---")
        config_block = stdout[config_start:config_end + len("--- End Config ---")]
        assert_lt("Config block size", len(config_block), 800, " chars")

    # Status block should always be present and small
    status_start = stdout.find("--- Memory Hook Status ---")
    status_end = stdout.find("--- End Status ---")
    if status_start >= 0 and status_end >= 0:
        status_block = stdout[status_start:status_end + len("--- End Status ---")]
        assert_lt("Status block size", len(status_block), 300, " chars")

    teardown_vault()


def test_keyword_extraction_quality():
    """Keyword extraction should handle edge cases correctly."""
    print("\n=== test_keyword_extraction_quality ===")
    setup_vault_with_notes()

    # Test that what's doesn't produce 's' as a keyword
    stdout, _, rc, _ = run_hook("what's the status of the deployment?")
    keywords_line = [l for l in stdout.split("\n") if "Keywords:" in l]
    if keywords_line:
        keywords = keywords_line[0].split("Keywords:")[1].strip()
        assert_true(
            "No single-char keyword 's' from what's",
            " s " not in f" {keywords} " and not keywords.startswith("s "),
            f"Keywords: '{keywords}'"
        )

    teardown_vault()


def test_execution_time():
    """Hook should complete well within timeout."""
    print("\n=== test_execution_time ===")
    setup_vault_with_notes()

    timings = []
    for prompt in ["fix a bug", "remember the auth decision", "what do you know about deploy", "hi"]:
        _, _, _, elapsed = run_hook(prompt)
        timings.append(elapsed)

    avg = sum(timings) / len(timings)
    max_t = max(timings)

    assert_lt("Average hook time", avg, 0.5, "s")
    assert_lt("Max hook time", max_t, 1.0, "s")
    print(f"    Timings: avg={avg:.3f}s, max={max_t:.3f}s, all={[f'{t:.3f}' for t in timings]}")

    teardown_vault()


def test_total_injection_size():
    """Total context injected should be bounded."""
    print("\n=== test_total_injection_size ===")
    setup_vault_with_notes()

    # Relevant prompt — should have notes but still bounded
    stdout, _, _, _ = run_hook("auth decision tokens")
    assert_lt("Relevant prompt context size", len(stdout), 5000, " chars")

    # Irrelevant prompt — should be much smaller
    stdout, _, _, _ = run_hook("fix the CSS bug")
    assert_lt("Irrelevant prompt context size", len(stdout), 2000, " chars")

    teardown_vault()


def test_project_name_fallback_behavior():
    """When keywords match nothing, falling back to project name should be controlled."""
    print("\n=== test_project_name_fallback_behavior ===")
    setup_vault_with_notes()

    # Use a cwd that would produce a project name matching nothing useful
    stdout, _, _, _ = run_hook("fix the CSS bug", cwd="/tmp/some-random-project")
    note_expansions = stdout.count("[from:")

    assert_true(
        "No false-positive note expansion on project-name fallback",
        note_expansions == 0,
        f"Got {note_expansions} note expansions from project-name fallback"
    )

    teardown_vault()


def test_empty_vault_overhead():
    """Hook on an empty vault should be very lightweight."""
    print("\n=== test_empty_vault_overhead ===")
    global TEST_VAULT
    TEST_VAULT = Path(tempfile.mkdtemp(prefix="mem_empty_"))
    TEST_VAULT.mkdir(exist_ok=True)
    os.environ["CLAUDE_MEMORY_VAULT"] = str(TEST_VAULT)

    # Init the vault
    engine.VAULT_DIR = TEST_VAULT
    engine.cmd_init()

    stdout, _, rc, elapsed = run_hook("remember that we use PostgreSQL")
    assert_true("Empty vault hook succeeds", rc == 0)
    assert_lt("Empty vault execution time", elapsed, 0.5, "s")
    assert_lt("Empty vault context size", len(stdout), 1500, " chars")

    teardown_vault()


# --- Runner ---

def main():
    global PASS_COUNT, FAIL_COUNT

    tests = [
        test_false_positive_irrelevant_prompt,
        test_minimal_prompt_overhead,
        test_relevant_prompt_finds_notes,
        test_config_block_size,
        test_keyword_extraction_quality,
        test_execution_time,
        test_total_injection_size,
        test_project_name_fallback_behavior,
        test_empty_vault_overhead,
    ]

    print(f"Running {len(tests)} hook efficiency tests...\n")

    for test in tests:
        try:
            test()
        except Exception as e:
            FAIL_COUNT += 1
            print(f"  ERROR: {test.__name__} raised {type(e).__name__}: {e}")
        finally:
            teardown_vault()

    print(f"\n{'='*50}")
    print(f"Hook Efficiency Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print(f"{'='*50}")

    # Write results as JSON for the eval framework
    results = {
        "passed": PASS_COUNT,
        "failed": FAIL_COUNT,
        "total": PASS_COUNT + FAIL_COUNT,
        "pass_rate": PASS_COUNT / (PASS_COUNT + FAIL_COUNT) if (PASS_COUNT + FAIL_COUNT) > 0 else 0
    }
    results_path = Path(__file__).resolve().parent.parent / "evals" / "efficiency_results.json"
    results_path.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nResults written to: {results_path}")

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
