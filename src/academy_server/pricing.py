"""Cost of a call from its usage. Prices live only in pricing.yaml; runs store usage.

Arithmetic is done in Decimal: summing float dollars drifts (0.0014080000000000002).
Tiered prices (Haiku's input_over_100k) are not applied.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

MILLION = Decimal(1_000_000)


class Pricing:
    def __init__(self, models: dict[str, dict[str, Any]]):
        self.models = models

    @classmethod
    def load(cls, path: Path) -> "Pricing":
        with path.open(encoding="utf-8") as f:
            return cls((yaml.safe_load(f) or {}).get("models", {}))

    def cost_usd(self, model: str | None, usage: dict[str, Any] | None) -> float | None:
        """USD for one call, or None when the model has no price or there is no usage."""
        p = self.models.get(model or "")
        if not p or not usage:
            return None

        def tokens(key: str) -> Decimal:
            return Decimal(int(usage.get(key) or 0))

        def price(key: str) -> Decimal:
            return Decimal(str(p.get(key, 0)))

        # cache_creation_input_tokens covers both TTLs; the breakdown (if sent) says how many were 1h.
        breakdown = usage.get("cache_creation") or {}
        write_1h = Decimal(int(breakdown.get("ephemeral_1h_input_tokens") or 0))
        write_5m = tokens("cache_creation_input_tokens") - write_1h
        cost = (tokens("input_tokens") * price("input")
                + tokens("output_tokens") * price("output")
                + tokens("cache_read_input_tokens") * price("cache_read")
                + write_5m * price("cache_write_5m")
                + write_1h * price("cache_write_1h"))
        return float(cost / MILLION)
