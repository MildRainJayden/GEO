from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("perplexity", "perplexity-sim-2026-07", 0.88, 0.90, 0.60))
