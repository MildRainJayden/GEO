from .simulated import ProviderProfile, SimulatedProvider


def build_provider() -> SimulatedProvider:
    return SimulatedProvider(ProviderProfile("yuanbao", "hunyuan-sim-2026-07", 0.58, 0.52, 0.88))
