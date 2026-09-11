# PLM-C1 v0.3

- Added controlled noun/verb inflection matching, including consonant-y plurals.
- Added inspectable `NormalizationEvent` records and `NORMALIZE_MORPHOLOGY` operations.
- Added provisional, corrective, and retraction role patterns.
- Added `retracted` state and explicit `RETRACT` residual removal.
- Changed target transition handling from source-wide to clause-aware event identity.
- Added `TARGET_SHIFT` operation records.
- Added allowlisted `river*` compound analysis with `SEGMENT_COMPOUND` records.
- Added conservative open-set confidence when a domain has no matching Evidence.
- Preserved PLM-C1 v0.2, v0.1, and C0 v0.3 as frozen baselines.
- Added v0.3 feature and calibration ablations.
- Added a frozen 60-case post-implementation v0.3 challenge without post-run tuning.
- Expanded the test suite from 54 to 72 tests.
