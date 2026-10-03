# PRE-Step5C owner closeout (2026-09-05)

## Scope

This working tree includes Claude cleanup work and Codex corrective changes.
Repository evidence, independent fixtures and regression runs are the basis of
approval. No live restart or production state/lock/halt maintenance is included.
Step5C is a separate change, permitted only after this cleanup is committed.

## Observation contract

- ka20009 currently exposes a date and a local fetch timestamp, not verified
  market-side checkpoint time or finalized-close evidence. Such observations
  remain informational: CLOSE_UNVERIFIED / OBSERVED_UNVERIFIED_TIME.
- Verified components require positive finite prices, parseable timezone-aware
  market timestamps within the existing checkpoint tolerance, matching date,
  and a literal true finalized flag for close. Display and EOD calculation use
  the same authoritative close. Unknown or failed observations cannot enable
  legacy fallback; only genuinely never-attempted slots may fall back.
- Primary and closeout recovery each have a permanent exclusive claim receipt.
  A manifest ATTEMPT_INCOMPLETE is written before the read request. A crash
  cannot authorize replay. This intentionally trades a missed measurement for
  at-most-once logical acquisition; it is not exactly-once delivery.
- A completed missing/partial primary permits at most one separately claimed
  recovery. Day-level OS locking serializes manifest updates across slots.
  Corrupt files are not reset. Unfinished attempts require manual investigation.
- Physical HTTP read retries remain the existing reader policy and are not
  represented as a measured count. Mutation retry policy is unchanged.

## Execution and reporting

Canonical Scanner rank overrides stale legacy rank fields. Explicit Step5B
BrokerOutcome remains authoritative. Legacy fallback with insufficient or
contradictory evidence is UNKNOWN, never a guessed rejection or acceptance.
Board operation requires explicit authority; candidate identity alone does not
prove an active runtime. Validation failure, insufficient evidence and operation
status remain separate. No scoring, eligibility or risk thresholds change.

## Residual limitations

This patch does not add a verified index data provider. Consequently the actual
ka20009 close cannot yet complete verified forward evaluation. Claim files and
manifest storage must be on one local filesystem shared by collector processes;
network filesystems are not an approved locking backend. Power-loss durability
depends on the filesystem honoring flush/fsync and atomic replacement.
