# AI Development Provenance

## Purpose

This document defines how Human, Codex, Claude Code, and other AI-agent work is
credited from the pre-Claude refactoring baseline forward. It also constrains
historical attribution so repository history is not rewritten from memory or
tool assumptions.

## Core Principle

Attribution and technical verification are different claims.

- A Git diff can verify that a subsystem changed.
- Tests can verify behavior at a commit.
- Neither proves which AI agent authored the change.
- Git author metadata in this repository represents the committing human
  account and must not be treated as the AI implementer identity.

## Confidence Levels

### VERIFIED

Use only when repository evidence directly names the role and agent, such as:

- a committed provenance record
- an explicit auditor/owner line in a contemporaneous document
- a commit trailer or review artifact that identifies the agent

Example: the M31 readiness document explicitly records `Auditor: Codex`.

### SUPPORTED

Use when several repository signals strongly support the attribution but do not
prove every task or commit.

Example: from `2026-04-07`, `docs/dev/workflow.md` states:

```text
Codex implements
Gemini reviews
Codex finalizes
```

This supports the phrase `Codex-centered workflow`. It does not authorize
blanket `Implementation: Codex` on every later commit.

### UNCERTAIN

Use when a branch name, task-oriented document, writing style, or isolated
reference suggests an agent but lacks direct provenance.

### UNKNOWN

Use when the repository cannot identify the implementing or reviewing agent.
This is the correct state for much of the initial history.

## Historical Attribution Boundary

### Before the first Git commit

M1-M13 chronology is reconstructed from archived plans and retrospective patch
notes. The exact implementation sequence and AI agent are `UNCERTAIN` or
`UNKNOWN`.

### 2026-02-12 through 2026-04-06

Milestones can be verified through Git, code, and tests, but broad agent
attribution is `UNKNOWN`. The explicit M31 `Auditor: Codex` statement applies to
that audit only.

### From 2026-04-07

The committed workflow supports this description:

```text
Development Process : Codex-centered workflow
Confidence          : SUPPORTED
```

Individual changes still require their own evidence before using:

```text
Implementation : Codex
Confidence     : VERIFIED
```

### Claude Code Boundary

No repository evidence was found that assigns pre-baseline implementation to
Claude Code. Claude Code work starts only when an approved post-baseline task
records that role. A later Claude audit finding is an audit finding, not a fact
merely because Claude reported it; it must be reproduced against code,
contracts, tests, or runtime artifacts.

## Roles

### Human

- product direction and success criteria
- architecture acceptance
- trading-risk acceptance
- approval of behavior changes and promotion decisions
- final merge and release approval
- resolution of conflicting AI reviews

### Claude Code

- repository archaeology when assigned
- architecture and dependency audit when assigned
- refactoring design or implementation when assigned
- review of Codex work when assigned
- production of reproducible audit findings with evidence

### Codex

- repository archaeology and architecture analysis when assigned
- implementation when assigned
- tests and regression verification when assigned
- review of Claude Code work when assigned
- operational diagnosis and documentation when assigned

### Other AI Agents

Other agents, including Gemini, are recorded by actual task role and evidence.
No permanent mapping such as `Claude = design` and `Codex = implementation` is
allowed.

## Owner and Reviewer Model

Every significant change should identify task roles, not permanent agent jobs.

```text
Owner           : Human or assigned AI agent
Analysis        : named participant(s)
Design          : named participant(s)
Implementation  : named participant(s)
Review          : named participant(s)
Verification    : named participant(s) + automated tests
Final Approval  : Human
```

An agent can be owner on one change and reviewer on another. Cross-model review
should identify both the reviewed commit and the review evidence.

## Evidence Requirements by Claim

| Claim | Minimum evidence |
| --- | --- |
| Milestone existed | Git commit/diff plus matching path |
| Behavior was implemented | Source plus deterministic test or runtime artifact |
| Agent implemented change | Explicit committed provenance or equivalent direct record |
| Agent reviewed change | Review artifact naming reviewer and reviewed ref |
| Human approved change | Merge/approval record or explicit committed decision |
| Audit finding is valid | Reproduction against code, tests, contracts, or artifacts |

## Prohibited Attribution Practices

- Do not infer AI identity from Git author.
- Do not infer authorship from prose style or commit volume.
- Do not retroactively mark all commits on a `codex/*` branch as verified Codex
  implementation.
- Do not turn workflow policy into proof of each historical task.
- Do not assign Claude Code credit for pre-baseline work without evidence.
- Do not rewrite existing historical patch-note entries to improve attribution.

## Future Change Policy

Use `change_provenance_template.yaml` for architecture, runtime, strategy,
execution, guard, contract, deployment, and other material changes. It is not
required for typo-only or mechanically generated changes.

The provenance record should be committed with the implementation or review,
and should point to:

- baseline or parent commit
- changed components
- behavior-impact classification
- verification commands/results
- owner/reviewer roles
- final Human approval state

## Cross-Model Review

When Claude Code and Codex review each other:

1. Freeze the reviewed commit hash.
2. Record findings as `confirmed`, `not_reproduced`, `design_question`, or
   `accepted_risk`.
3. Require source/test/artifact evidence for a confirmed finding.
4. Keep audit findings separate from applied fixes.
5. Record which agent implemented and which agent reviewed the fix.

This prevents an AI statement from becoming architecture truth without
repository evidence.
