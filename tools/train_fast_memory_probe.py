"""Small synthetic training/gradient check; explicitly NOT pi05 or robot evidence."""

import argparse
import json
from pathlib import Path

import torch
from torch import nn

from cpswm.simulation.fast_memory import AlternatingMemoryTrainer, ObservationFastMemory


def batch(seed, size=64):
    g = torch.Generator().manual_seed(seed)
    labels = torch.randint(0, 2, (size,), generator=g)
    x = torch.zeros(4, size, 4)
    x[0, :, 0] = 1
    x[0, :, 1] = labels * 2.0 - 1.0
    x[1:, :, 2] = 1
    x[:, :, 3] = torch.randn(4, size, generator=g) * 0.05
    return x, labels


def evaluate(memory, policy, *, intervention, seed=92001):
    x, y = batch(seed, 512)
    state = memory.reset(len(y))
    with torch.no_grad():
        for index, frame in enumerate(x):
            if index == len(x) - 1:
                if intervention == "reset":
                    state = memory.reset(len(y))
                elif intervention == "shuffle":
                    state = state.roll(1, 0)
                elif intervention == "opposite_history":
                    opposite = x.clone()
                    opposite[0, :, 1] *= -1
                    state = memory.reset(len(y))
                    for prior in opposite[:-1]:
                        _, state = memory(prior, state)
            read, state = memory(frame, state)
        logits = policy(torch.cat((x[-1], read), -1))
    return float((logits.argmax(-1) == y).float().mean())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("new output required")
    a.output.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.manual_seed(7301)
    memory = ObservationFastMemory(4, 16)
    policy = nn.Sequential(nn.Linear(20, 32), nn.Tanh(), nn.Linear(32, 2))
    # Stage 1: current cue is visible; train action capability without memory.
    optimizer = torch.optim.Adam(policy.parameters(), lr=0.01)
    for step in range(100):
        x, y = batch(1000 + step)
        optimizer.zero_grad()
        logits = policy(torch.cat((x[0], torch.zeros(len(y), 16)), -1))
        loss = nn.functional.cross_entropy(logits, y)
        loss.backward()
        optimizer.step()
    trainer = AlternatingMemoryTrainer(memory, policy, learning_rate=0.01)
    losses = []
    for cycle in range(5):
        for phase in ("memory", "policy"):
            for step in range(40):
                x, y = batch(2000 + cycle * 100 + step)
                losses.append(
                    {"cycle": cycle, "phase": phase, "loss": trainer.step(x, y, phase=phase)}
                )
    result = {
        "evidence": "synthetic delayed-cue action classification; not VLA or robotics",
        "torch": torch.__version__,
        "cuda": torch.cuda.is_available(),
        "mps": torch.backends.mps.is_available(),
        "slow_seed": 7301,
        "evaluation_seed": 92001,
        "accuracy": {
            mode: evaluate(memory, policy, intervention=mode)
            for mode in ("intact", "reset", "shuffle", "opposite_history")
        },
        "losses": losses,
        "pi05_trained": False,
        "remaining": [
            "pi05 action-expert interface",
            "compatible action demonstrations",
            "full VLA alternating training",
        ],
    }
    (a.output / "result.json").write_text(json.dumps(result, indent=2))
    torch.save(
        {"memory": memory.state_dict(), "policy": policy.state_dict()}, a.output / "probe.pt"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "losses"}, indent=2))


if __name__ == "__main__":
    main()
