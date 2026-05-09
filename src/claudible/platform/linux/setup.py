"""Linux setup backend — delegates to setup/checks.py (apt-based)."""

from __future__ import annotations

from claudible.platform.base import SetupBackend


class AptSetup(SetupBackend):
    """apt-based setup checks for Linux."""

    def check_system_deps(self) -> bool:
        from claudible.setup.checks import check_system_deps

        return check_system_deps()

    def check_input_permissions(self, auto_yes: bool = False) -> bool:
        from claudible.setup.checks import check_input_group

        return check_input_group(auto_yes)

    def get_system_info(self) -> dict:
        from claudible.setup.checks import _get_gpu_info, _get_ram_gb

        return {
            "gpu": _get_gpu_info(),
            "ram_gb": _get_ram_gb(),
        }
