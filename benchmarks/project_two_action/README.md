# Project-two action benchmark v0.2

Authoritative runner:

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_action_death_test.py
```

The runner constructs a provenance-safe D0 replay pilot, tunes each method only
on the validation split, opens the sealed test split only after tuning, and
emits per-case, aggregate, worst-group, paired-difference and 95% bootstrap-CI
records. O-STaR, DynaMem and STAR are explicitly labelled `reduced_skill_proxy`;
they are not mixed with faithful/matched baseline claims.

No external dataset is selected by this directory.
