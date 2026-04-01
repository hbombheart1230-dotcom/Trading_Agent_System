# Pre-Buy Strategist Refresh Note
## Why this should be handled with Phase 5-3 policy ownership work

---

## 1. Purpose

This note captures a runtime observation from live monitoring:

- the system often reuses cached strategist context/news,
- scanner continues to recompute rankings every cycle,
- and top candidates can rotate within the same cached strategist frame.

The question is not whether strategist/news should run every minute.
The more precise question is:

**should strategist/news refresh once immediately before a real BUY-capable decision path?**

This note does **not** change the roadmap and does **not** replace Phase 5-3.
It records why this idea is better treated as a **Phase 5-3-adjacent policy ownership problem**, not as an isolated hotfix.

---

## 2. Current Runtime Behavior

Observed behavior:

- strategist output is cached in persisted state,
- commander frequently reuses cached strategist output on `cached_strategist` paths,
- scanner still recalculates candidate ranking each cycle,
- monitor/execution can therefore act on a scanner decision that was made under a strategist/news context that is not freshly regenerated for that exact BUY moment.

In practice this means:

- news/playbook context can remain stable for several minutes,
- while selected symbols can still move among a small candidate set,
- making the system look like it is "re-ranking under old strategist context".

This is not necessarily wrong, but it creates a real question about **entry-time freshness**.

---

## 3. Why the User Concern Is Valid

The concern is operationally reasonable:

- strategist/news context does not need to refresh every minute,
- but a real BUY-capable moment is more sensitive than ordinary WAIT cycles,
- so using a stale strategist/news frame immediately before BUY may be weaker than desired.

A practical interpretation is:

- keep cache reuse for normal cycle efficiency,
- but consider forcing a strategist/news refresh when the system is close to actual entry.

That is a valid design direction.

---

## 4. Why This Should Not Be Treated As A Small Standalone Patch

A "pre-BUY strategist refresh" sounds small, but it crosses multiple ownership boundaries:

1. commander cache reuse policy
- commander currently decides when cached strategist output is reused.

2. strategist invocation timing
- strategist/news refresh timing is currently part of commander/runtime flow, not monitor-only logic.

3. policy ownership
- if strategist refresh is tied to BUY-capable states, the trigger condition should be aligned with official entry policy ownership.

4. provenance/audit clarity
- if a BUY used freshly refreshed strategist context, artifacts should clearly show that the run used refreshed context rather than cached context.

Because of that, implementing this as an isolated tactical patch now would risk introducing:

- hidden commander/runtime coupling,
- unclear provenance,
- duplicated "entry readiness" logic in the wrong layer.

---

## 5. Why Phase 5-3 Is The Better Fit

Phase 5-3 is the stage where policy ownership becomes explicit.
That makes it the natural place to decide:

- who owns the decision to refresh strategist/news,
- what exact condition qualifies as "BUY-capable enough" to justify refresh,
- whether refresh is triggered by commander, monitor, or a policy handoff rule,
- and how refreshed-vs-cached strategist context is recorded in provenance.

This is a policy/orchestration question more than a UI/reporting question.
So it fits Phase 5-3 much better than Phase 5-2 or Phase 5-2-2.

---

## 6. Recommended Direction For Later Work

Do not implement minute-by-minute strategist refresh.

Instead, consider a later rule shaped like:

- normal case: cached strategist allowed,
- near-entry case: force one strategist/news refresh before final BUY-capable evaluation,
- post-refresh result must be clearly tagged in artifacts/provenance.

Candidate trigger families to evaluate later:

- monitor legacy decision is close to BUY,
- shadow/scoring decision is BUY-capable,
- scanner + monitor compatibility indicates near-entry convergence,
- or commander explicitly requests a final context refresh before allowing BUY.

The exact trigger should be decided only when policy ownership is formalized.

---

## 7. Explicit Boundary

This note does **not** recommend:

- changing strategist schema now,
- changing scanner scoring now,
- changing monitor thresholds now,
- inserting ad-hoc refresh calls directly into monitor,
- or bypassing commander cache policy with local exceptions.

Those would blur ownership before Phase 5-3.

---

## 8. Practical Conclusion

The idea is valid.

But the right interpretation is:

**"Pre-BUY strategist/news refresh" should be treated as a Phase 5-3 policy/orchestration topic, not as a standalone quick patch.**

Until then:

- keep current cached strategist behavior,
- keep observing whether candidate rotation under cached context is materially harmful,
- and defer actual implementation until policy ownership and provenance rules are being formalized.
