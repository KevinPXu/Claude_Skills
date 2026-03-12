---
tags: [claude-memory, project]
summary: Context command uses bidirectional BFS with convergence scoring — BM25 seeds, forward/backlink expansion, score-based budget
---
# Graph Traversal Algorithm

## Current Implementation
- BM25 seeds (FTS5) with normalized scores
- Forward links from seeds: score * 0.5 decay
- Backlinks to seeds: score * 0.4 decay
- Notes reachable from multiple seeds accumulate score (convergence)
- Hub notes excluded from expansion
- Budget-aware output: seeds get full content, others get summary

## Future Options Discussed
- Personalized PageRank (PPR): random walk with restart, better for 200+ note vaults
- Spreading activation: single-pass charge propagation with degree normalization
- TF-IDF seed improvement: already achieved via FTS5 BM25

## Links
- [[sqlite-engine-migration]]
- [[obsidian-memory]]
- [[atomicity-approach]]
