"""Read-only score diagnosis; extracted live archive paths, not a runtime factor."""
import json
import sys
from pathlib import Path
from uuid import UUID

import numpy as np
import torch

from cpswm.perception_mapping.natural_vision import NaturalAppearanceDetector

torch.set_num_threads(2)
base, weights = Path(sys.argv[1]), Path(sys.argv[2])
detector = NaturalAppearanceDetector(
    weights_path=weights, household_id=UUID(int=1), session_id=UUID(int=2), trace_id=UUID(int=3)
)
rows = []
for trial in ("live", "live-targeted", "live-small-view"):
    for index in (4, 5):
        rgb = np.load(base / trial / f"transport/evaluator_only/sdk-events/{index:03}-rgb.npy", allow_pickle=False)
        with torch.inference_mode():
            prediction = detector._model([torch.from_numpy(rgb.copy()).permute(2, 0, 1).float() / 255])[0]
        items = [
            dict(category=detector._categories[int(label)], score_uncalibrated=float(score), box=box.tolist())
            for label, score, box in zip(prediction["labels"], prediction["scores"], prediction["boxes"], strict=True)
        ]
        rows.append(dict(
            trial=trial, index=index,
            accepted_at_existing_threshold=sum(i["score_uncalibrated"] >= 0.5 for i in items),
            top5=items[:5], highest_bottle=next((i for i in items if i["category"] == "bottle"), None)
        ))
print(json.dumps(dict(
    purpose="Read-only offline score diagnosis on already collected public pixels; no threshold/model/runtime update",
    existing_threshold=0.5, rows=rows
), indent=2))
