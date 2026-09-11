# PLM-C2 v0.1

- Added a typed Claim Graph with Source, Clause, Event, Entity, Concept, Evidence, and Relation nodes.
- Added graph edge integrity checks and node/edge audit metrics.
- Added decimal-safe period sentence boundaries.
- Added temporal event transitions and explicit `event_links`.
- Added C2 revision roles for `originally` and `revised` patterns.
- Added irregular lemma normalization for `bitten`.
- Added allowlisted closed-compound handling for `riverbank(s)`.
- Added typed `RELATION_GATE` for non-spatial river evidence near ambiguous `bank`.
- Preserved C1 v0.3/v0.2/v0.1 and C0 v0.3 as frozen baselines.
- Added seven C2 mechanism ablations plus a graph-presence ablation.
- Added a frozen 60-case post-implementation C2 challenge without post-run tuning.
- Expanded the test suite from 72 to 92 tests.
