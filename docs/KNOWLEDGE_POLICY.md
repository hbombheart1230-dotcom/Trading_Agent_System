# Knowledge / Obsidian Policy

## Purpose

`docs/` is both the repository documentation tree and the Obsidian vault. There is one document tree, not a parallel knowledge repository.

The authority direction is one way:

```text
runtime and canonical truth
        ->
authoritative documentation
        ->
knowledge navigation and Obsidian views
```

Runtime must never depend on Obsidian notes.

## Rules

1. **Do not duplicate authority.** Link to existing architecture, contract, evaluation, safety, or runtime documents instead of copying their detail into a milestone, ADR, or operation note.
2. **Milestones summarize current state.** They answer where the work is, what is frozen, what is active, and what is next.
3. **ADRs explain durable decisions.** Create one only when the architectural reason would otherwise be unclear to a future maintainer.
4. **Operations notes record concise findings.** They state what happened, impact, current status, and follow-up. Raw logs remain in their source artifacts.
5. **Reports are not independent evidence by default.** Derived reports do not create a second evidence sample.
6. **No runtime dependency.** No production code, guard, strategy, or execution decision may read `docs/` or an Obsidian vault for behavioral authority.
7. **Update the knowledge layer selectively.** Update it after a material milestone change, ADR, formal freeze, important operational finding, or roadmap/current-next change. Do not update it for every code edit or test pass.
8. **Self-PASS is not formal freeze.** The lifecycle is:

   ```text
   IMPLEMENTED
   -> AWAITING INDEPENDENT AUDIT
   -> FORMALLY FROZEN
   ```

   Only an independent audit may record a formal freeze. Policy documents must not embed live milestone examples that become stale.
9. **Personal Obsidian state stays unmanaged.** Do not commit `.obsidian/` workspace files, caches, plugin state, or local UI state.

## Navigation

- [[00_HOME|Documentation home]]
- [[UEF]]
- [[Strategy_Program_Integration|Strategy Program Integration]]
- [[Safety]]
- [[Reporter_Q100|Reporter Q100]]

## Related Authority

- [Architecture V2](architecture/architecture_v2.md)
- [Evaluation roadmap](en/12_roadmap.md)
- [UEF-4A legacy family inventory](research/uef4_legacy_family_inventory.md)
