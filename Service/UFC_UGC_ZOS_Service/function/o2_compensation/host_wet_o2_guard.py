"""Host-side protection for abnormal wet-basis oxygen readings.

The supplier O2 implementation can be replaced independently.  This guard
therefore lives in the host application and runs before compensation, so a
communication truncation cannot contaminate the dry-basis calculation.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping


class WetOxygenAnomalyGuard:
    """Filter wet-basis O2 jumps after a configurable warm-up period."""

    def __init__(
        self,
        enabled: bool = True,
        jump_threshold: float = 0.15,
        warmup_cycles: int = 3,
        log: Callable[[str], None] | None = None,
    ):
        self.enabled = bool(enabled)
        self.jump_threshold = max(0.0, float(jump_threshold))
        self.warmup_cycles = max(0, int(warmup_cycles))
        self._log = log or (lambda message: None)
        self.completed_cycles = 0
        self._last_accepted: dict[str, float] = {}

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Mapping[str, object]] | None,
        log: Callable[[str], None] | None = None,
    ) -> "WetOxygenAnomalyGuard":
        section = (config or {}).get("O2_ANOMALY", {})

        def as_bool(value, default=True):
            if isinstance(value, bool):
                return value
            if value is None:
                return default
            return str(value).strip().lower() in {"1", "true", "yes", "on"}

        def as_float(value, default):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def as_int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            enabled=as_bool(section.get("enabled"), True),
            jump_threshold=as_float(section.get("wet_o2_jump_threshold"), 0.15),
            warmup_cycles=as_int(section.get("warmup_cycles"), 3),
            log=log,
        )

    def reset(self) -> None:
        """Clear the per-experiment history without changing configuration."""
        self.completed_cycles = 0
        self._last_accepted.clear()

    def complete_cycle(self) -> int:
        """Mark one complete REF + selected-cage round as finished."""
        self.completed_cycles += 1
        return self.completed_cycles

    @staticmethod
    def _as_valid_number(value) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number <= 0.0 or number > 100.0:
            return None
        return number

    def filter(self, channel: str, value) -> tuple[object, bool]:
        """Return ``(value, replaced)`` for one wet-basis channel sample.

        During warm-up, valid samples establish the per-channel baseline but
        are never jump-filtered.  Afterwards, only a jump from the last
        accepted numeric sample is replaced.  A missing/invalid sample uses
        that previous value when available; otherwise it remains unchanged.
        """
        if not self.enabled:
            return value, False

        current = self._as_valid_number(value)
        previous = self._last_accepted.get(channel)

        if current is None:
            if previous is None:
                return value, False
            self._log(
                f"湿基氧异常保护：{channel} 当前值无效，使用前一有效值 {previous:.3f}"
            )
            return round(previous, 3), True

        if self.completed_cycles < self.warmup_cycles:
            self._last_accepted[channel] = current
            return current, False

        if previous is not None:
            delta = abs(current - previous)
            if delta > self.jump_threshold:
                self._log(
                    f"湿基氧异常保护：{channel} 当前值 {current:.3f} 与前值 "
                    f"{previous:.3f} 相差 {delta:.3f}，超过阈值 "
                    f"{self.jump_threshold:.3f}，使用前值"
                )
                return round(previous, 3), True

        self._last_accepted[channel] = current
        return current, False

