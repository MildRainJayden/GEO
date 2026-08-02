from __future__ import annotations

import json
import os


DEFAULT_PROVIDER_MAU_WEIGHTS: dict[str, float] = {
    "doubao": 38230,
    "qwen": 16718,
    "deepseek": 12982,
    "yuanbao": 4984,
    "kimi": 1800,
}
DEFAULT_UNKNOWN_PROVIDER_MAU = 2000.0
DEFAULT_MAU_BLEND = 0.7


def provider_weight_config() -> dict[str, float]:
    configured = dict(DEFAULT_PROVIDER_MAU_WEIGHTS)
    configured.update(_parse_weight_overrides(os.environ.get("AIVC_PROVIDER_MAU_WEIGHTS", "")))
    return configured


def provider_raw_mau(provider: str) -> float:
    configured = provider_weight_config()
    return max(0.0, configured.get(_normalize_provider(provider), _unknown_provider_mau()))


def normalized_provider_weights(providers: list[str]) -> dict[str, float]:
    unique = sorted({_normalize_provider(provider) for provider in providers if provider})
    if not unique:
        return {}
    if len(unique) == 1:
        return {unique[0]: 1.0}

    mau_values = {provider: provider_raw_mau(provider) for provider in unique}
    mau_total = sum(mau_values.values()) or 1.0
    mau_share = {provider: value / mau_total for provider, value in mau_values.items()}
    equal_share = 1 / len(unique)
    blend = _mau_blend()
    weights = {
        provider: blend * mau_share[provider] + (1 - blend) * equal_share
        for provider in unique
    }
    total = sum(weights.values()) or 1.0
    return {provider: value / total for provider, value in weights.items()}


def _parse_weight_overrides(raw: str) -> dict[str, float]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _parse_compact_weights(text)
    if not isinstance(payload, dict):
        return {}
    return {
        _normalize_provider(name): float(value)
        for name, value in payload.items()
        if str(name).strip() and _is_number(value)
    }


def _parse_compact_weights(raw: str) -> dict[str, float]:
    weights: dict[str, float] = {}
    for item in raw.replace("；", ";").replace("，", ",").split(","):
        if not item.strip() or ":" not in item:
            continue
        name, value = item.split(":", 1)
        try:
            weights[_normalize_provider(name)] = float(value)
        except ValueError:
            continue
    return weights


def _unknown_provider_mau() -> float:
    raw = os.environ.get("AIVC_UNKNOWN_PROVIDER_MAU", "")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_UNKNOWN_PROVIDER_MAU


def _mau_blend() -> float:
    raw = os.environ.get("AIVC_PROVIDER_MAU_BLEND", "")
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return DEFAULT_MAU_BLEND


def _normalize_provider(provider: str) -> str:
    return str(provider or "").strip().lower()


def _is_number(value: object) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
