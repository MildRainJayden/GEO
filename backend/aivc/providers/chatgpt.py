from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("chatgpt", "gpt-sim-2026-07", 0.84, 0.77, 0.55))
