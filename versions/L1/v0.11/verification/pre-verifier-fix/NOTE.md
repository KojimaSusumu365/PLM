# Verification log parser correction

Under source freeze `d411cd32f5dc7b03c02d0781807c472ed5ac8346382fc0a66dbcf1a88ccd95b1`, two complete numerical runs succeeded with digest `e6e9616ad7f5d82bd07692f2229c8e1a0d3b07ee73f34f9249fae8325dca7a2d`. Both contained 683 fitted conditions and 12,068 passing accounting/contract/control checks. Seven result/model files were byte-identical; their hashes are preserved here.

The subsequent release verifier passed the unit-test subprocess but failed to parse its count: unittest writes its summary to stderr, while the helper returned stdout only. The saved combined log already included both streams. Correction: return the combined stdout and stderr to the parser. This is a release-verifier-only change; no numerical implementation, dataset, threshold, seed, or selection policy changed.

Because verify_release.py is included in the source freeze, the corrected release is refrozen and the full numerical runs are repeated rather than relabeling the old results as having run under a new freeze. Earlier complete result directories remain in work. This directory preserves the original verifier, freeze, repeatability and summaries as audit evidence, not as final release results.
