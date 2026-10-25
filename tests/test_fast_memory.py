# ruff: noqa: E402
import pytest

torch = pytest.importorskip("torch")
from cpswm.simulation.fast_memory import AlternatingMemoryTrainer, ObservationFastMemory


def test_read_before_write_mask_and_episode_reset():
    torch.manual_seed(7)
    memory = ObservationFastMemory(3, 4)
    state = memory.reset(2)
    initial = state.clone()
    x = torch.randn(2, 3)
    read, updated = memory(x, state, write_mask=torch.tensor([True, False]))
    assert torch.equal(state, initial)
    assert torch.equal(read, torch.zeros_like(read))
    assert not torch.equal(updated[0], state[0])
    assert torch.equal(updated[1], state[1])
    assert torch.equal(memory.reset(2), initial)
    next_read, _ = memory(x, updated)
    assert next_read[0].abs().sum() > 0
    with pytest.raises(ValueError):
        memory(x, state, write_mask=torch.ones(2))


def test_inner_update_matches_autograd_associative_gradient():
    memory = ObservationFastMemory(3, 4)
    x = torch.randn(2, 3)
    state = memory.reset(2)
    key = torch.nn.functional.normalize(memory.key(x), dim=-1)
    value = torch.tanh(memory.value(x))
    loss = 0.5 * (torch.bmm(key.unsqueeze(1), state).squeeze(1) - value).square().sum()
    (gradient,) = torch.autograd.grad(loss, state, retain_graph=True)
    _, updated = memory(x, state)
    assert torch.allclose(updated, state - torch.sigmoid(memory.log_step) * gradient)


def test_alternation_freezes_counterpart_without_breaking_write_gradient():
    torch.manual_seed(19)
    memory = ObservationFastMemory(3, 4)
    policy = torch.nn.Linear(7, 2)
    trainer = AlternatingMemoryTrainer(memory, policy)
    x, labels = torch.randn(3, 8, 3), torch.arange(8) % 2
    for phase in ("memory", "policy", "memory"):
        old_m = [p.detach().clone() for p in memory.parameters()]
        old_p = [p.detach().clone() for p in policy.parameters()]
        assert trainer.step(x, labels, phase=phase) > 0
        changed_m = any(
            not torch.equal(a, b) for a, b in zip(old_m, memory.parameters(), strict=True)
        )
        changed_p = any(
            not torch.equal(a, b) for a, b in zip(old_p, policy.parameters(), strict=True)
        )
        assert (changed_m, changed_p) == (phase == "memory", phase == "policy")
        if phase == "memory":
            assert memory.key.weight.grad.abs().sum() > 0
            assert memory.value.weight.grad.abs().sum() > 0
