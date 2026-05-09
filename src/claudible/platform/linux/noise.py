"""Linux noise suppression backend — delegates to stt/noise.py (PipeWire/RNNoise)."""

from __future__ import annotations

from typing import Any

from claudible.platform.base import NoiseBackend


class PipeWireNoise(NoiseBackend):
    """PipeWire RNNoise-based noise suppression for Linux."""

    def is_available(self) -> bool:
        from claudible.stt.noise import is_rnnoise_installed

        return is_rnnoise_installed()

    def is_active(self) -> bool:
        from claudible.stt.noise import is_rnnoise_active

        return is_rnnoise_active()

    def enable(self, **kwargs: Any) -> bool:
        from claudible.stt.noise import enable_rnnoise

        return enable_rnnoise(**kwargs)

    def disable(self) -> bool:
        from claudible.stt.noise import disable_rnnoise

        return disable_rnnoise()
