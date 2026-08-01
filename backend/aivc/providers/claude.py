from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("claude", "claude-sim-2026-07", 0.76, 0.69, 0.48))
