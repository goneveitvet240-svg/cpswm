# CIAV accuracy–cost break-even preregistration — 2026-08-28

## Frozen question

Does CIAV have a non-trivial accuracy–cost region in which it beats never-act
on net utility under 15% symmetric actor misattribution while preserving clean
and ambiguous safety?

This is a synthetic mechanism falsifier, not an external-validity claim.

## Frozen method

- CIAV maximum verifications per episode: 4
- Minimum CF-BOCPD actor/identity attribution-shift mass: 0.75
- Dual-timescale action readout: fast 0.8, surviving slow 0.2
- Identity-switch evidence: unavailable and fixed to zero
- Comparator: never-act on the same episodes and evidence transformation
- Steps per episode: 32
- Evaluation seeds: 18000–18011, not previously inspected

No parameter is selected on these evaluation seeds.

## Frozen surface

- Quick-check sensitivity = specificity: `{0.75, 0.85, 0.95}`
- Identity-aware sensitivity = specificity: `min(0.99, quick + 0.12)`
- Common multiplier on motion, time, interruption, privacy, and safety costs:
  `{0.25, 0.50, 0.75, 1.00}`
- Stress cells: clean, ambiguous, 15% symmetric misattribution

The practical candidate region excludes optimistic corners:

- quick-check accuracy `<= 0.85`; and
- cost multiplier `>= 0.50`.

## Frozen pointwise pass rule

A surface point passes only if all conditions hold:

1. Under misattribution, CIAV net utility is strictly above never-act.
2. Under misattribution, put-back error and owner-habit contamination do not
   exceed never-act.
3. Under clean and ambiguous evidence, put-back error and contamination do not
   exceed never-act.
4. Under clean and ambiguous evidence, CIAV net-utility loss relative to
   never-act is no worse than `-0.0025` per step.

## Frozen direction-level gate

Continue CIAV toward larger confirmation only if the practical candidate
region contains at least three passing points and those points span at least
two accuracy levels and at least two cost levels. A single point, a high-
accuracy-only strip, or a near-zero-cost-only strip is a no-go.

Whatever the result, the grid and gate will not be changed after reading seeds
18000–18011.
