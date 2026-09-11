# PLM-C0 v0.2 Evaluation Report

Dataset cases: **36**

| Metric | PLM-C0 v0.2 | Positive lexical baseline | Delta |
|---|---:|---:|---:|
| top1_accuracy | 1.0 | 0.6944 | 0.3056 |
| top5_recall | 1.0 | 0.9444 | 0.0556 |
| mrr | 0.9444 | 0.875 | 0.0694 |
| unresolved_precision | 1.0 | 0.2857 | 0.7143 |
| unresolved_recall | 1.0 | 0.8 | 0.2 |
| minority_evidence_retention | 1.0 | 1.0 | 0.0 |
| contradiction_rejection | 1.0 | 0.8 | 0.2 |
| average_candidates_evaluated | 4.33 | 4.33 | 0.0 |
| average_patterns_checked | 53.53 | 50.92 | 2.61 |

## Definitions

- Top-1 uses the final selected Concept, including `UNRESOLVED`.
- Top-5 and MRR rank only a gold Concept with observable positive signal; an unsupported zero-score row does not count.
- For an expected `UNRESOLVED`, rank is 1 only when the model abstains.
- Minority evidence retention is Top-5 retention on cases tagged `minority_evidence`.
- Contradiction rejection requires the selected Concept not to be one of the case's explicitly forbidden Concepts.
- Candidates evaluated counts all Concepts scored in the target domain. Patterns checked counts configured lexical/context rules visited.

## Errors

- None
