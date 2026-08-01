from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("kimi", "kimi-sim-2026-07", 0.68, 0.64, 0.78))
