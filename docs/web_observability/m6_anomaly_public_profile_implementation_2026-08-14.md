# M6 Anomaly and Public Profile Implementation - 2026-08-14

## Scope

M6 adds an operations-facing anomaly read model and a server-enforced public
showcase profile. It does not change Scanner, Strategist, Monitor, Commander,
order execution, Q evaluation, memory, or report generation behavior.

New read-only endpoints:

```text
GET /api/v1/anomalies?day=YYYY-MM-DD
GET /api/v1/profile
```

The Web adds `Operations Alerts` and places the highest-priority signals on
the Overview page. All anomaly output is `OBSERVATION_ONLY`.

## Anomaly Contract

`operational_anomaly.v1` uses existing normalized Trade and Opportunity read
models. The rules are intentionally simple, deterministic, and explainable.

| Category | v1 rule | Severity | Cost basis |
| --- | --- | --- | --- |
| Data freshness | During 08:50-16:10 KST, runtime event age above 300 seconds; critical above 900 seconds or source missing | Warning/Critical | N/A |
| Artifact integrity | Trade read model reports one or more source issues | Warning | N/A |
| Cost spike | Price return minus broker-truth mock net return exceeds 0.50 percentage points | Warning | MOCK_BROKER_NET |
| Repeated loss | Same symbol reaches two consecutive losses in the selected day | Warning | MOCK_BROKER_NET |
| Early loss exit | Negative-return trade closes in less than 60 seconds | Warning | MOCK_BROKER_NET |
| Missed opportunity | Prospective shadow candidate was not traded and observed +30m mock net return exceeds 0.30% | Watch | MOCK_BROKER_NET |

These are operating review signals, not automatic diagnoses or trading
instructions. Missing evidence produces `NO_DATA` or `PARTIAL`; it is not
treated as a clean bill of health. Every item contains the observed value,
threshold, comparator, sample count, source, and stable anomaly ID.

## Public Profile Contract

The profile is selected only by the API process environment:

```text
OBSERVABILITY_EXPOSURE_PROFILE=private  # default
OBSERVABILITY_EXPOSURE_PROFILE=public
```

There is no request query parameter or UI switch that can bypass the server
profile. Public mode:

* keeps the same Portfolio, Performance, Trade, Opportunity, Strategy, Market,
  and Anomaly formulas as private mode;
* always identifies execution as `SIMULATION_MOCK`, read-only, and not
  execution-callable;
* disables report catalog contents and raw report content;
* removes account, order, fill, run, process, host, path, prompt, response,
  credential, and environment identifiers from JSON responses;
* hides private-only LLM Operations, Reports, and Data Quality navigation;
* marks the console `PUBLIC SHOWCASE`.

The sanitizer is a final defense boundary. Domain response models already omit
the sensitive fields, and public report access is blocked before file content
is read.

## Module Boundaries

```text
apps/api/adapters/source_freshness.py
apps/api/domain/anomaly_rules.py              # compatibility facade
apps/api/domain/anomalies/
  policy.py
  factory.py
  trade_sequence_rule.py
  trade_exit_rule.py
  trade_cost_rule.py
  opportunity_rules.py
  freshness_rules.py
  integrity_rules.py
apps/api/models/anomalies.py
apps/api/services/anomalies.py
apps/api/routers/anomalies.py

apps/api/infrastructure/public_sanitization.py
apps/api/infrastructure/public_middleware.py
apps/api/models/profile.py
apps/api/services/profile.py
apps/api/routers/profile.py

apps/web/src/features/alerts/
```

No Trading Core or evaluation implementation module is imported.

## Verification Gate

M6 must keep these checks green:

* API regression and isolation tests;
* deterministic anomaly classification tests;
* public report-content denial and recursive redaction tests;
* GET-only route scan and zero Trading Core imports;
* Web unit tests, strict TypeScript, and production build;
* desktop/mobile browser smoke for all product routes;
* unchanged Trading Runtime PID and active artifact cadence.

## Deliberate Limits

M6 does not estimate unsupported explicit cost fields, infer private account
identifiers, or convert a shadow opportunity into realized performance. The
thresholds are versioned policy constants. Changing them requires a separate
observability review; it must never silently alter trading behavior.
