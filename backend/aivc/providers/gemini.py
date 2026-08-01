from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("gemini", "gemini-sim-2026-07", 0.78, 0.75, 0.50))
