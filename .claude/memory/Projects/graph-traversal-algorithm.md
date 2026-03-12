---
tags: [claude-memory, project]
summary: Context uses PPR + Steiner hybrid — BM25 seeds, PageRank clustering, Steiner tree pruning to minimum subgraph
---
# Graph Traversal Algorithm

## Implementation (PPR + Steiner Hybrid)
1. BM25 seeds via FTS5 with porter stemming and column weighting
2. Personalized PageRank (alpha=0.3, 10 iterations) — degree-normalized random walk with restart on seeds
3. Top-K PPR candidates passed to Steiner tree approximation
4. Steiner prunes to minimum subgraph connecting seeds — drops dangling notes
5. Budget-aware output: seeds get full content, non-seeds get summary only

## Key Properties
- Degree normalization dampens hubs automatically (no special-casing needed)
- Convergence: notes reachable from multiple seeds accumulate PPR score
- Alpha controls cluster tightness (0.3 = tight, 0.1 = broad)
- Graceful degradation: on small/empty vaults, collapses to just returning seeds
- 44 unit tests covering edge cases, cluster separation, performance

## Links
- [[sqlite-engine-migration]]
- [[obsidian-memory]]
- [[atomicity-approach]]
