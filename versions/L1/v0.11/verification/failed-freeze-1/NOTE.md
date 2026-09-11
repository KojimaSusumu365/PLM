# First frozen run stopped: unknown validation vocabulary

Initial freeze: `114479c19af51a04f773533c3b71e6e26613bdac2698b6be74d7bf0ebbe5b634`.

Both attempts stopped at the small-training parity3 condition, after 480 fitted conditions. The failure was `ValueError: unknown_validation_value` from training.py. A nuisance field happened to contain only one value in the eight training rows, while validation/calibration included its other value. No final result JSON or result digest was produced.

Correction: keep the training vocabulary unchanged. During candidate validation, rows containing unseen values count as abstentions; calibration similarly treats unknown-field-value rejection as abstention. The ordinary query/packet vocabulary boundary stays strict. Data, representation, dimensions, seeds, candidate policy, margins and risk target were not altered. Two regression tests cover this boundary. Full evaluation is restarted under a new freeze.

Original training.py, test_v011.py and SOURCE_FREEZE.json are preserved here. Incomplete saved-model directories from the first attempts are retained in work, not represented as final evidence.
