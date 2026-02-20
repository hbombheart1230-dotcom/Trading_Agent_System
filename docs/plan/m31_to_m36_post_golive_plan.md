# M31-M36 Post-GoLive Program Plan

- Date: 2026-02-20
- Scope: post-M30 operating model for stability, scale, governance automation, and continuous improvement.
- Entry gate: M30 production readiness sign-off completed.

## M31: Post-GoLive Stabilization

- Objective:
  - stabilize production behavior after go-live and reduce incident frequency/MTTR.
- Deliverables:
  - first 2-4 weeks incident review loop and recurring postmortem template
  - SLO baseline calibration (`availability`, `latency`, `error-budget`) and runbook updates
  - on-call severity ladder and escalation ownership matrix
  - alert noise reduction pass (false-positive and duplicate suppression tuning)
- Exit criteria:
  - incident triage/ownership is deterministic and error-budget consumption is measurable daily

## M32: Performance and Cost Optimization

- Objective:
  - improve decision/execution responsiveness and reduce inference/ops cost under stable behavior.
- Deliverables:
  - hot-path latency profiling (strategist/scanner/monitor/execution boundaries)
  - LLM token/cost optimization policy (model tiering, prompt compression, cache strategy)
  - API rate-control tuning based on `429` telemetry and burst traffic shape
  - cost-per-run and cost-per-intent reporting in daily/weekly ops summaries
- Exit criteria:
  - p95 runtime latency and per-run cost show sustained improvement against M30 baseline

## M33: Capital Allocation and Risk Expansion

- Objective:
  - evolve from single-policy sizing to portfolio-aware capital allocation.
- Deliverables:
  - volatility-aware position sizing policy and dynamic notional cap
  - strategy-level and symbol-level risk budget envelopes
  - allocation simulation harness with scenario replay (trend/range/high-vol regimes)
  - promotion gate for allocation policy changes with downside constraints
- Exit criteria:
  - multi-strategy capital usage remains within risk envelopes during replay and controlled pilot

## M34: Market and Broker Expansion

- Objective:
  - extend runtime to multi-broker/multi-market operations without contract regressions.
- Deliverables:
  - broker adapter contract v2 (`quote/order/status/fill`) with compatibility tests
  - account/broker routing policy in Commander/Supervisor boundary
  - per-market calendar/session handling and symbol normalization rules
  - cross-broker fallback policy and operator failover playbook
- Exit criteria:
  - at least one additional broker/market path runs through canonical contracts and safety gates

## M35: Governance and Compliance Automation

- Objective:
  - automate audit/compliance checks as default runtime behavior, not periodic manual work.
- Deliverables:
  - policy-as-code checks for approvals, guard overrides, and real-mode exceptions
  - signed audit bundles (decision->intent->execution trace + config snapshot)
  - retention and access-control enforcement checks in scheduled jobs
  - compliance evidence export pack for periodic internal review
- Exit criteria:
  - compliance evidence and policy violations are auto-detected and review-ready without manual stitching

## M36: Autonomous Operations and Self-Healing

- Objective:
  - reach supervised-autonomy operations with controlled self-healing.
- Deliverables:
  - automated health manager for restart/failover/degrade recovery actions
  - adaptive guardrails based on error-budget and incident trend
  - closed-loop ops controller for alert policy/retry/rate-limit tuning suggestions
  - quarterly resilience drill automation (chaos scenarios + recovery verification)
- Exit criteria:
  - system can recover from predefined failure classes with minimal operator intervention and auditable decisions

## Suggested Cadence

1. M31-M32: stabilize and optimize current stack.
2. M33-M34: scale capital and market coverage safely.
3. M35-M36: automate governance and recovery operations.

## Next Action

1. Create `M31-1` implementation note for SLO baseline and incident-review workflow.
2. Add one operator script that generates weekly post-go-live health summary from event and alert artifacts.
