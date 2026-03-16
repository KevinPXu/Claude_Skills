---
tags: [claude-memory, pattern]
summary: Over-explaining internals in a skill gives the model enough to reason itself into the wrong behavior
created: 2026-03-16
updated: 2026-03-16
---


# Pattern: Over-Explanation Causes Reasoning Regression

## What Happened
Added a "Recall with graph traversal" section to obsidian-memory SKILL.md explaining
that $MEM context uses BM25 via memory_engine.py. An eval agent then used grep instead:

> "BM25 runs via engine → hook invokes engine → hook not running → fall back to grep"

The old skill had no explanation — just a table entry "User asks what do you know → $MEM search".
Agents followed it without overthinking. Pass rate: old 100%, new 75%.

## Fix
One sentence removed the bad reasoning path:
"$MEM is a standalone CLI, not hook-dependent."

Pass rate recovered to 100%.

## Rule
Explain WHAT to do, not HOW it works internally.
The more implementation detail you include, the more surface area for the model
to reason itself out of the correct behavior.

## Applies To
Any skill where the correct action is a specific command/tool and
the temptation is to explain the underlying mechanism.

## Links
- [[obsidian-memory]]
- [[python-hook-audit]]
- [[Patterns]]
