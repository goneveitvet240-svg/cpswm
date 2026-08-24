# Project-two action benchmark v0.2

Authoritative runner:

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_action_death_test.py
```

The runner constructs a provenance-safe D0 replay pilot, tunes each method only
on the validation split, opens the sealed test split only after tuning, and
emits per-case, aggregate, worst-group, paired-difference and 95% bootstrap-CI
records. O-STaR, DynaMem and STAR are labelled `matched_replay_adapter`; the
report records their missing faithful inputs and excludes them from a
paper-superiority claim. AMG remains the strongest faithful matched arm in D0.

No external dataset is selected by this directory.
