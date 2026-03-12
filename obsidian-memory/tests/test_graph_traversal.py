#!/usr/bin/env python3
"""
Thorough tests for PPR + Steiner hybrid graph traversal.

Tests cover:
  - Empty/fresh vaults (0 notes)
  - Single note vaults
  - Small vaults (2-5 notes)
  - Disconnected components
  - Hub note exclusion
  - Convergence scoring (multi-path reachability)
  - Steiner tree pruning (only essential connectors)
  - Budget limits
  - Performance on larger synthetic graphs
  - Regression: hook integration end-to-end
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add bin/ to path so we can import the engine
ENGINE_DIR = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(ENGINE_DIR))

import memory_engine as engine

# --- Test infrastructure ---

TEST_VAULT = None
PASS_COUNT = 0
FAIL_COUNT = 0


def setup_vault():
    """Create a fresh temp vault for testing."""
    global TEST_VAULT
    TEST_VAULT = Path(tempfile.mkdtemp(prefix="mem_test_"))
    engine.VAULT_DIR = TEST_VAULT
    os.environ["CLAUDE_MEMORY_VAULT"] = str(TEST_VAULT)
    return TEST_VAULT


def teardown_vault():
    """Remove temp vault."""
    global TEST_VAULT
    if TEST_VAULT and TEST_VAULT.exists():
        shutil.rmtree(TEST_VAULT)
    TEST_VAULT = None


def write_note(path, content):
    """Write a note directly to the test vault."""
    full = TEST_VAULT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)


def fresh_db():
    """Get a fresh DB connection with synced index."""
    db_path = TEST_VAULT / engine.DB_NAME
    if db_path.exists():
        db_path.unlink()
    conn = engine.get_db()
    engine.sync_index(conn)
    return conn


def assert_eq(name, actual, expected):
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        PASS_COUNT += 1
        print(f"  PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name}")
        print(f"    expected: {expected}")
        print(f"    actual:   {actual}")


def assert_true(name, condition):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name}")


def assert_in(name, item, collection):
    global PASS_COUNT, FAIL_COUNT
    if item in collection:
        PASS_COUNT += 1
        print(f"  PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name}")
        print(f"    {item!r} not in {collection!r}")


def assert_not_in(name, item, collection):
    global PASS_COUNT, FAIL_COUNT
    if item not in collection:
        PASS_COUNT += 1
        print(f"  PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name}")
        print(f"    {item!r} should not be in {collection!r}")


# --- Tests ---


def test_empty_vault():
    """PPR and Steiner on an empty vault with no notes."""
    print("\n=== test_empty_vault ===")
    setup_vault()
    TEST_VAULT.mkdir(exist_ok=True)
    conn = fresh_db()

    scores = engine.personalized_pagerank(conn, [])
    assert_eq("PPR with no seeds returns empty", scores, {})

    scores = engine.build_context_graph(conn, [])
    assert_eq("build_context_graph with no seeds returns empty", scores, {})

    tree = engine.steiner_tree(conn, set(), [])
    assert_eq("Steiner with no seeds returns empty", tree, set())

    teardown_vault()


def test_single_note():
    """Vault with one note, one seed."""
    print("\n=== test_single_note ===")
    setup_vault()

    write_note("Projects/auth.md", "---\ntags: [claude-memory]\nsummary: Auth decision\n---\n# Auth\nChose JWT.\n")
    conn = fresh_db()

    seeds = [("Projects/auth.md", -1.0)]
    scores = engine.personalized_pagerank(conn, seeds)

    assert_in("Single note appears in PPR", "Projects/auth.md", scores)
    assert_true("Single note has positive score", scores.get("Projects/auth.md", 0) > 0)

    result = engine.build_context_graph(conn, seeds)
    assert_in("Single note in context graph", "Projects/auth.md", result)

    teardown_vault()


def test_two_linked_notes():
    """Two notes linking to each other."""
    print("\n=== test_two_linked_notes ===")
    setup_vault()

    write_note("Projects/auth.md", "---\nsummary: Auth choice\n---\n# Auth\nChose JWT. See [[tokens]].\n")
    write_note("Projects/tokens.md", "---\nsummary: Token storage\n---\n# Tokens\nStored in httpOnly cookies. See [[auth]].\n")
    conn = fresh_db()

    seeds = [("Projects/auth.md", -1.0)]
    scores = engine.personalized_pagerank(conn, seeds)

    assert_in("Seed note in PPR results", "Projects/auth.md", scores)
    assert_in("Linked note discovered via PPR", "Projects/tokens.md", scores)
    assert_true("Seed scores higher than linked",
                scores.get("Projects/auth.md", 0) > scores.get("Projects/tokens.md", 0))

    teardown_vault()


def test_hub_exclusion():
    """Hub notes should be excluded from traversal results."""
    print("\n=== test_hub_exclusion ===")
    setup_vault()

    write_note("Index.md", "---\ntags: [index]\n---\n# Index\n- [[Projects]]\n- [[auth]]\n")
    write_note("Projects.md", "---\ntags: [category]\n---\n# Projects\n- [[auth]]\n")
    write_note("Projects/auth.md", "---\nsummary: Auth\n---\n# Auth\nJWT. [[Index]]\n[[Projects]]\n")
    conn = fresh_db()

    seeds = [("Projects/auth.md", -1.0)]
    scores = engine.build_context_graph(conn, seeds)

    assert_not_in("Index.md excluded from results", "Index.md", scores)
    assert_not_in("Projects.md excluded from results", "Projects.md", scores)
    assert_in("Actual note still present", "Projects/auth.md", scores)

    teardown_vault()


def test_disconnected_components():
    """Seeds in disconnected components should all appear."""
    print("\n=== test_disconnected_components ===")
    setup_vault()

    write_note("Projects/auth.md", "---\nsummary: Auth\n---\n# Auth\nJWT.\n")
    write_note("Projects/deploy.md", "---\nsummary: Deploy\n---\n# Deploy\nDocker.\n")
    # No links between them
    conn = fresh_db()

    seeds = [("Projects/auth.md", -1.0), ("Projects/deploy.md", -0.8)]
    scores = engine.build_context_graph(conn, seeds)

    assert_in("First disconnected seed present", "Projects/auth.md", scores)
    assert_in("Second disconnected seed present", "Projects/deploy.md", scores)

    # Steiner tree should return both even though disconnected
    tree = engine.steiner_tree(conn, {"Projects/auth.md", "Projects/deploy.md"},
                                list(scores.keys()))
    assert_in("Disconnected seed 1 in Steiner tree", "Projects/auth.md", tree)
    assert_in("Disconnected seed 2 in Steiner tree", "Projects/deploy.md", tree)

    teardown_vault()


def test_convergence_scoring():
    """Note reachable from multiple seeds should score higher than single-path notes."""
    print("\n=== test_convergence_scoring ===")
    setup_vault()

    write_note("Projects/auth.md", "---\nsummary: Auth\n---\n# Auth\n[[shared-pattern]]\n")
    write_note("Projects/api.md", "---\nsummary: API\n---\n# API\n[[shared-pattern]]\n")
    write_note("Projects/shared-pattern.md", "---\nsummary: Shared\n---\n# Shared\nUsed by both.\n")
    write_note("Projects/unrelated.md", "---\nsummary: Unrelated\n---\n# Only linked from auth\n")
    # auth links to shared-pattern and unrelated
    # api links to shared-pattern only
    write_note("Projects/auth.md", "---\nsummary: Auth\n---\n# Auth\n[[shared-pattern]]\n[[unrelated]]\n")
    conn = fresh_db()

    seeds = [("Projects/auth.md", -1.0), ("Projects/api.md", -0.9)]
    scores = engine.personalized_pagerank(conn, seeds)

    shared = scores.get("Projects/shared-pattern.md", 0)
    unrelated = scores.get("Projects/unrelated.md", 0)

    assert_true("Convergent note (shared) scores higher than single-path (unrelated)",
                shared > unrelated)

    teardown_vault()


def test_steiner_pruning():
    """Steiner should keep connecting nodes and drop unconnected ones."""
    print("\n=== test_steiner_pruning ===")
    setup_vault()

    # Chain: auth -> middleware -> api
    # Dangling: auth -> logging (not connected to api)
    write_note("Projects/auth.md", "---\nsummary: Auth\n---\n# Auth\n[[middleware]]\n[[logging]]\n")
    write_note("Projects/middleware.md", "---\nsummary: Middleware\n---\n# Middleware\n[[auth]]\n[[api]]\n")
    write_note("Projects/api.md", "---\nsummary: API\n---\n# API\n[[middleware]]\n")
    write_note("Projects/logging.md", "---\nsummary: Logging\n---\n# Logging\n[[auth]]\n")
    conn = fresh_db()

    seed_paths = {"Projects/auth.md", "Projects/api.md"}
    candidates = ["Projects/auth.md", "Projects/middleware.md", "Projects/api.md", "Projects/logging.md"]

    tree = engine.steiner_tree(conn, seed_paths, candidates)

    assert_in("Seed auth in tree", "Projects/auth.md", tree)
    assert_in("Seed api in tree", "Projects/api.md", tree)
    assert_in("Connector middleware in tree", "Projects/middleware.md", tree)
    assert_not_in("Dangling logging pruned from tree", "Projects/logging.md", tree)

    teardown_vault()


def test_steiner_single_seed():
    """Steiner with 1 seed returns just that seed."""
    print("\n=== test_steiner_single_seed ===")
    setup_vault()
    write_note("Projects/auth.md", "---\nsummary: Auth\n---\n# Auth\n")
    conn = fresh_db()

    tree = engine.steiner_tree(conn, {"Projects/auth.md"}, ["Projects/auth.md"])
    assert_eq("Single seed returns set of one", tree, {"Projects/auth.md"})

    teardown_vault()


def test_full_context_pipeline():
    """End-to-end: BM25 -> PPR -> Steiner -> output."""
    print("\n=== test_full_context_pipeline ===")
    setup_vault()

    write_note("Projects/auth.md",
        "---\ntags: [claude-memory, project]\nsummary: Auth decision JWT\n---\n"
        "# Auth Decision\nChose JWT over sessions.\n## Links\n- [[tokens]]\n- [[refresh]]\n")
    write_note("Projects/tokens.md",
        "---\ntags: [claude-memory, project]\nsummary: Token storage in httpOnly cookies\n---\n"
        "# Token Storage\nhttpOnly cookies.\n## Links\n- [[auth]]\n")
    write_note("Projects/refresh.md",
        "---\ntags: [claude-memory, project]\nsummary: Refresh token rotation strategy\n---\n"
        "# Refresh Strategy\nRotating refresh tokens.\n## Links\n- [[auth]]\n- [[tokens]]\n")
    write_note("Projects/deploy.md",
        "---\ntags: [claude-memory, project]\nsummary: Docker deployment setup\n---\n"
        "# Deploy\nDocker compose.\n")
    write_note("Index.md", "---\ntags: [index]\n---\n# Index\n- [[auth]]\n- [[deploy]]\n")
    write_note("Projects.md", "---\ntags: [category]\n---\n# Projects\n- [[auth]]\n- [[tokens]]\n- [[refresh]]\n- [[deploy]]\n")
    conn = fresh_db()

    seeds = engine.search_bm25(conn, "auth tokens", 5)
    assert_true("BM25 finds auth-related seeds", len(seeds) > 0)

    scores = engine.build_context_graph(conn, seeds)

    assert_not_in("Hub Index.md excluded", "Index.md", scores)
    assert_not_in("Hub Projects.md excluded", "Projects.md", scores)

    # Deploy should NOT appear — it's unrelated to auth/tokens
    assert_not_in("Unrelated deploy note excluded", "Projects/deploy.md", scores)

    # Auth-related notes should all appear
    auth_related = {"Projects/auth.md", "Projects/tokens.md", "Projects/refresh.md"}
    found = set(scores.keys()) & auth_related
    assert_true("At least 2 auth-related notes found", len(found) >= 2)

    teardown_vault()


def test_ppr_dead_ends():
    """PPR handles dead-end nodes (no outgoing links) gracefully."""
    print("\n=== test_ppr_dead_ends ===")
    setup_vault()

    write_note("Projects/parent.md", "---\nsummary: Parent\n---\n# Parent\n[[leaf]]\n")
    write_note("Projects/leaf.md", "---\nsummary: Leaf\n---\n# Leaf\nNo outgoing links.\n")
    conn = fresh_db()

    seeds = [("Projects/parent.md", -1.0)]
    scores = engine.personalized_pagerank(conn, seeds)

    assert_in("Parent in results", "Projects/parent.md", scores)
    assert_in("Leaf discovered", "Projects/leaf.md", scores)
    assert_true("Total probability sums to ~1",
                abs(sum(scores.values()) - 1.0) < 0.05)

    teardown_vault()


def test_ppr_score_distribution():
    """PPR scores should sum to approximately 1 (probability distribution)."""
    print("\n=== test_ppr_score_distribution ===")
    setup_vault()

    write_note("a.md", "---\nsummary: A\n---\n# A\n[[b]]\n[[c]]\n")
    write_note("b.md", "---\nsummary: B\n---\n# B\n[[a]]\n[[c]]\n")
    write_note("c.md", "---\nsummary: C\n---\n# C\n[[a]]\n")
    conn = fresh_db()

    seeds = [("a.md", -1.0)]
    scores = engine.personalized_pagerank(conn, seeds)
    total = sum(scores.values())

    assert_true(f"PPR scores sum to ~1.0 (got {total:.3f})", abs(total - 1.0) < 0.1)
    assert_true("Seed has highest score",
                scores.get("a.md", 0) >= max(scores.get("b.md", 0), scores.get("c.md", 0)))

    teardown_vault()


def test_larger_synthetic_graph():
    """Performance and correctness on a 50-note graph with clusters."""
    print("\n=== test_larger_synthetic_graph ===")
    setup_vault()

    # Create two clusters: auth-cluster (notes 0-19) and deploy-cluster (notes 20-39)
    # Plus 10 noise notes (40-49) with no links
    for i in range(20):
        links = []
        if i > 0:
            links.append(f"[[auth-{i-1}]]")
        if i < 19:
            links.append(f"[[auth-{i+1}]]")
        # Cross-links within cluster
        if i % 5 == 0 and i + 3 < 20:
            links.append(f"[[auth-{i+3}]]")
        link_str = "\n".join(f"- {l}" for l in links)
        write_note(f"Projects/auth-{i}.md",
            f"---\nsummary: Auth component {i}\n---\n# Auth {i}\nAuthentication part {i}.\n{link_str}\n")

    for i in range(20):
        links = []
        if i > 0:
            links.append(f"[[deploy-{i-1}]]")
        if i < 19:
            links.append(f"[[deploy-{i+1}]]")
        link_str = "\n".join(f"- {l}" for l in links)
        write_note(f"Projects/deploy-{i}.md",
            f"---\nsummary: Deploy component {i}\n---\n# Deploy {i}\nDeployment part {i}.\n{link_str}\n")

    for i in range(10):
        write_note(f"Projects/noise-{i}.md",
            f"---\nsummary: Noise {i}\n---\n# Noise {i}\nIrrelevant note.\n")

    conn = fresh_db()

    note_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    assert_eq("50 notes indexed", note_count, 50)

    # Search for auth — should find auth cluster, not deploy or noise
    seeds = engine.search_bm25(conn, "authentication auth", 5)
    assert_true("BM25 finds auth seeds", len(seeds) > 0)

    t0 = time.time()
    scores = engine.build_context_graph(conn, seeds)
    elapsed = time.time() - t0

    assert_true(f"Completed in <1s ({elapsed:.3f}s)", elapsed < 1.0)

    # Check cluster separation
    auth_found = [p for p in scores if "auth-" in p]
    deploy_found = [p for p in scores if "deploy-" in p]
    noise_found = [p for p in scores if "noise-" in p]

    assert_true(f"Auth cluster notes found ({len(auth_found)})", len(auth_found) > 0)
    assert_eq("No deploy cluster notes leaked", len(deploy_found), 0)
    assert_eq("No noise notes leaked", len(noise_found), 0)

    teardown_vault()


def test_hook_integration():
    """End-to-end test through the hook (context-loader.sh)."""
    print("\n=== test_hook_integration ===")
    setup_vault()

    # Init vault structure
    write_note("Index.md", "---\ntags: [index]\n---\n# Index\n- [[Projects]]\n")
    write_note("Projects.md", "---\ntags: [category]\n---\n# Projects\n- [[myapp]]\n")
    write_note("Projects/myapp.md",
        "---\ntags: [claude-memory, project]\nsummary: My app uses React and PostgreSQL\n---\n"
        "# My App\nReact frontend, PostgreSQL backend.\n## Links\n- [[Projects]]\n")

    hook_path = Path(__file__).resolve().parent.parent / "hooks" / "context-loader.sh"
    input_json = json.dumps({"prompt": "what do you know about myapp", "cwd": str(TEST_VAULT)})

    env = os.environ.copy()
    env["CLAUDE_MEMORY_VAULT"] = str(TEST_VAULT)
    env["OBSIDIAN_MEMORY_SCRIPT"] = str(ENGINE_DIR / "obsidian-memory.sh")

    result = subprocess.run(
        ["bash", str(hook_path)],
        input=input_json, capture_output=True, text=True, env=env, timeout=10
    )

    output = result.stdout
    assert_true("Hook exits successfully", result.returncode == 0)
    assert_true("Context header present", "Memory Context for:" in output)
    assert_true("Config block present", "Obsidian Memory Config" in output)
    assert_true("Note content loaded", "React frontend" in output or "myapp" in output.lower())

    teardown_vault()


def test_bidirectional_discovery():
    """Notes should be found via backlinks, not just forward links."""
    print("\n=== test_bidirectional_discovery ===")
    setup_vault()

    # child links TO parent, but parent doesn't link to child
    write_note("Projects/parent.md", "---\nsummary: Parent project\n---\n# Parent\nThe main project.\n")
    write_note("Projects/child.md", "---\nsummary: Child detail\n---\n# Child\nDetail about parent. [[parent]]\n")
    conn = fresh_db()

    seeds = [("Projects/parent.md", -1.0)]
    scores = engine.personalized_pagerank(conn, seeds)

    assert_in("Child found via backlink to parent", "Projects/child.md", scores)

    teardown_vault()


def test_alpha_tightness():
    """Higher alpha should produce tighter clusters (more score on seeds)."""
    print("\n=== test_alpha_tightness ===")
    setup_vault()

    write_note("a.md", "---\nsummary: A\n---\n# A\n[[b]]\n")
    write_note("b.md", "---\nsummary: B\n---\n# B\n[[c]]\n")
    write_note("c.md", "---\nsummary: C\n---\n# C\n[[d]]\n")
    write_note("d.md", "---\nsummary: D\n---\n# D\nFar away.\n")
    conn = fresh_db()

    seeds = [("a.md", -1.0)]

    # Test with tight alpha
    old_alpha = engine.PPR_ALPHA
    engine.PPR_ALPHA = 0.5
    tight_scores = engine.personalized_pagerank(conn, seeds)

    # Test with loose alpha
    engine.PPR_ALPHA = 0.1
    loose_scores = engine.personalized_pagerank(conn, seeds)

    engine.PPR_ALPHA = old_alpha  # restore

    tight_seed_ratio = tight_scores.get("a.md", 0) / (sum(tight_scores.values()) or 1)
    loose_seed_ratio = loose_scores.get("a.md", 0) / (sum(loose_scores.values()) or 1)

    assert_true(f"Tight alpha concentrates more on seed ({tight_seed_ratio:.2f} > {loose_seed_ratio:.2f})",
                tight_seed_ratio > loose_seed_ratio)

    teardown_vault()


# --- Runner ---

def main():
    global PASS_COUNT, FAIL_COUNT

    tests = [
        test_empty_vault,
        test_single_note,
        test_two_linked_notes,
        test_hub_exclusion,
        test_disconnected_components,
        test_convergence_scoring,
        test_steiner_pruning,
        test_steiner_single_seed,
        test_full_context_pipeline,
        test_ppr_dead_ends,
        test_ppr_score_distribution,
        test_larger_synthetic_graph,
        test_hook_integration,
        test_bidirectional_discovery,
        test_alpha_tightness,
    ]

    print(f"Running {len(tests)} tests...\n")

    for test in tests:
        try:
            test()
        except Exception as e:
            FAIL_COUNT += 1
            print(f"  ERROR: {test.__name__} raised {type(e).__name__}: {e}")
        finally:
            teardown_vault()

    print(f"\n{'='*40}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print(f"{'='*40}")

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
