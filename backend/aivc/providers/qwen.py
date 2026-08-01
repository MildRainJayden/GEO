from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("qwen", "qwen-sim-2026-07", 0.72, 0.70, 0.80))
