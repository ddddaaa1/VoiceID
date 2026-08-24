# ADR 0009: Report Wilson intervals for locked-threshold error rates

- Status: Accepted
- Date: 2026-08-25

## Context

The first public VoiceID experiment contains only 30 genuine and 30 impostor trials in each partition. A point estimate of zero observed errors must not be interpreted as proof that the underlying error probability is zero. The report needs a deterministic uncertainty estimate without adding a heavyweight statistics dependency.

## Decision

Report two-sided 95% Wilson score intervals for FAR and FRR at the threshold selected on development. The confidence level is an explicit CLI parameter and the JSON report records the method, level, lower bound, and upper bound.

Do not attach these intervals to observed EER or minimum DCF. Those values also optimize a threshold on the reported partition, so a simple binomial interval would omit threshold-selection uncertainty.

## Consequences

Zero errors in 30 trials produces a nonzero upper bound instead of a misleading claim of zero risk. The implementation is deterministic and uses only the Python standard library.

Wilson intervals treat trials as binomial observations. VoiceID trials reuse speakers and templates, so observations are correlated and the effective sample size can be smaller than the trial count. The report therefore remains an exploratory corpus measurement. A larger protocol should add speaker-cluster bootstrap intervals and broader condition coverage.
