"""UEF-6A — Population Dedup Detection.

A READ-ONLY side-car detector over canonical ``EpisodeRecord`` populations
(as produced by the frozen UEF-5.2 historical recompute's ``episodes.jsonl``).
Mechanically detects when the same underlying physical episode is
represented/countable more than once across programs or rows, using the
EXISTING frozen UEF-1 identity model (``canonical_event_id`` /
``evaluation_subject_id`` / ``evaluation_record_id`` /
``classify_duplicate_relation()``) -- no new identity hierarchy is
introduced, and ``cross_program_link_key`` is never used as duplicate
authority.

This package never modifies ``EpisodeRecord``, ``AggregateRecord``, UEF-3
aggregation, UEF-5.2 recompute outputs, legacy artifacts, or trading
runtime. Its outputs are derived evidence only -- never new runtime
authority, and never fed into live trading.
"""
