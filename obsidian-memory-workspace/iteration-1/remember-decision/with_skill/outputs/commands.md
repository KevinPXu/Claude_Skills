# Commands Run — New Skill

```bash
$MEM search "Claude Skills config manager"
$MEM context "Claude Skills"
# Context followed links: Claude-Skills.md → Projects.md, Preferences.md, Patterns.md → Filesystem-Over-API.md
$MEM append "Projects/Claude-Skills.md" "## Config Manager Decision (2026-03-11)
- Switched from REST API calls to direct filesystem access for config manager
- **Reasoning**: Removes dependency on Obsidian running, makes the tool fully portable
- This aligns with the broader [[Filesystem-Over-API]] pattern
- [[Preferences]]"
$MEM read "Projects/Claude-Skills.md"  # verify
```
