# PLM-C1 v0.2

- Added parity-based English/Japanese polarity composition and `polarity_depth`.
- Added `asserted`, `provisional`, `corrective`, and `hypothetical` discourse states.
- Added `target_id` and target-scoped conflict isolation.
- Added inspectable `RelationEvidence` with connection, polarity, state, and application result.
- Added conservative spatial-relation gating for river-bank context.
- Added limited regular English plural matching and mixed ASCII/Japanese boundaries.
- Added `POLARITY_COMPOSE`, `STATE_TRANSITION`, and `RELATE` operation records.
- Preserved PLM-C1 v0.1 and PLM-C0 v0.3 as frozen in-package baselines.
- Added five v0.2 feature ablations plus the existing residual ablation.
- Added a frozen 60-case post-implementation v0.2 challenge; no model/data tuning after its first run.
- Expanded the test suite from 38 to 54 tests.
