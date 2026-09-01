# Project-two AMG action-interface fairness audit preregistration

## Frozen audit questions

1. Does the current action benchmark pass actor posteriors to matched AMG where
   its contract expects likelihoods?
2. Does that semantic mismatch change decisions on the present D0 distribution?
3. After AMG and PCHMP receive the same sticky latest-owner action readout, does
   AMG retain its advantage under actor-evidence stress?
4. Does execution feedback help or harm PCHMP relative to the feedback-blind AMG?
5. Is the evaluator target structurally aligned with a sticky latest-owner rule?

## Frozen arms

- AMG with the current posterior-as-likelihood adapter.
- AMG with prior-corrected odds `LR/(1+LR)`, where
  `LR=posterior/reference-prior`.
- Robot-visible actor-posterior threshold plus common sticky-owner readout.
- PCHMP owner mass plus common sticky-owner readout, with feedback.
- PCHMP owner mass plus common sticky-owner readout, without feedback.
- PCHMP native latest-owner reversible readout, with feedback.

All arms choose a put-back location from the same encounter-ordered location
set. Search reads the same latest observed location. Never does evaluator truth
enter a method.

## Frozen tuning and data

- AMG role fallback grid: `{0.20, 0.33, 0.50}`.
- Owner threshold grid for direct/PCHMP arms: `{0.40, 0.50, 0.60}`.
- Validation seeds: 19000–19003.
- One-time holdout seeds: 20000–20011.
- Stress cells: clean, ambiguous, deterministic 15% symmetric actor swap.
- Primary metric: put-back error; secondary metrics: regret, contamination,
  binary owner-classification error, false-owner and false-non-owner rates.

## Frozen interpretation

- Privileged information requires a visible-input or feedback-availability
  advantage that favors AMG.
- Privileged action interface requires AMG to choose from a more favorable
  scored action set or prediction timing.
- Target-alignment advantage is present if, after the first step, evaluator
  owner-habit truth follows the recurrence: update to the observed location on
  owner events and persist on non-owner events.
- If posterior and prior-corrected AMG are identical only because all
  reference priors are uniform, record the adapter as semantically wrong but
  empirically inert on D0.
- Record that passing raw likelihood ratios directly is invalid because AMG's
  current contract requires every score strictly inside `(0,1)`.
- If AMG still wins under the common sticky readout, attribute the residual to
  event inference/classification rather than action-interface privilege.
