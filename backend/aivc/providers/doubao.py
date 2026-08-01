from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("doubao", "doubao-sim-2026-07", 0.62, 0.58, 0.86))
